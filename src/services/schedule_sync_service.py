import pandas as pd
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Any, Optional

from src.database.supabase_client import db_manager
try:
    from src.database.supabase_client import fetch_outlook_schedules
except ImportError:
    fetch_outlook_schedules = None
from src.services.team_service import TeamService
from src.services.client_normalizer import parse_outlook_subject_to_client_and_task
from src.dashboard.common.ui_helpers import get_current_kst_time

class ScheduleSyncService:
    """
    아웃룩 일정과 카카오톡 실시간 작업 동기화 및 미래시 승격 서비스
    1. 카톡 미보고 작업 -> 일정표 시간대 도달 시 실시간 진행 작업으로 자동 승격
    2. 100% 진행률 도달 시 자동으로 완료(COMPLETED) 작업으로 전환
    3. 휴가/연차/반차 -> 실시간 진행 영역에 무조건 100%로 상시 표출
    """

    @classmethod
    def get_synced_live_tasks(
        cls,
        kakao_pend_df: pd.DataFrame,
        today_completed_df: pd.DataFrame,
        outlook_df: Optional[pd.DataFrame] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame, List[Dict[str, Any]]]:
        """
        카카오톡 진행 작업과 아웃룩 일정을 병합하여
        1) 최종 실시간 진행 작업 데이터프레임 (merged_pend_df)
        2) 아웃룩에서 100% 완료로 승격된 작업 데이터프레임 (auto_completed_df)
        3) 오늘 휴가/연차/반차 목록 (leave_records)
        을 반환
        """
        now = get_current_kst_time().replace(tzinfo=None)
        today_str = now.strftime("%Y-%m-%d")

        if outlook_df is None or outlook_df.empty:
            try:
                if hasattr(db_manager, "fetch_outlook_schedules"):
                    outlook_df = db_manager.fetch_outlook_schedules(today_str, today_str)
                elif fetch_outlook_schedules is not None:
                    outlook_df = fetch_outlook_schedules(today_str, today_str)
                else:
                    import importlib
                    import src.database.supabase_client as sc
                    importlib.reload(sc)
                    outlook_df = sc.db_manager.fetch_outlook_schedules(today_str, today_str)
            except Exception:
                outlook_df = pd.DataFrame()

        if outlook_df.empty or "start_time" not in outlook_df.columns:
            return kakao_pend_df, today_completed_df, pd.DataFrame(), []

        # 오늘 아웃룩 일정 필터링
        today_out = outlook_df.copy()
        if not pd.api.types.is_datetime64_any_dtype(today_out["start_time"]):
            today_out["start_time"] = pd.to_datetime(today_out["start_time"].astype(str).str.replace("T", " "), errors="coerce")
        if not pd.api.types.is_datetime64_any_dtype(today_out["end_time"]):
            today_out["end_time"] = pd.to_datetime(today_out["end_time"].astype(str).str.replace("T", " "), errors="coerce")

        today_out = today_out[today_out["start_time"].dt.strftime("%Y-%m-%d") == today_str]
        today_out = today_out.drop_duplicates(subset=["worker_name", "subject", "start_time"])

        promoted_pend_rows = []
        auto_completed_rows = []
        team_info = TeamService.get_team_members_info()

        # 1. 휴가/연차/반차 추출 (실시간 배너 및 오늘 완료된 작업에 100% 표출)
        leave_records = []
        leave_rows = today_out[today_out["is_leave"] == True]
        for _, r in leave_rows.iterrows():
            w_name = r["worker_name"]
            st_time = r["start_time"]
            ed_time = r["end_time"]
            st_dt = st_time.to_pydatetime() if hasattr(st_time, "to_pydatetime") else st_time
            ed_dt = ed_time.to_pydatetime() if hasattr(ed_time, "to_pydatetime") else ed_time
            l_type = r.get("leave_type") or "연차"
            if "반차" in str(l_type) or "반일" in str(l_type):
                dur_hours = 4.5
            elif "연차" in str(l_type) or "휴가" in str(l_type):
                dur_hours = 9.0
            else:
                dur_hours = float(r.get("duration_hours") or 9.0)
            w_title = team_info.get(w_name, {}).get("title", "")
            w_team = r.get("worker_team") or team_info.get(w_name, {}).get("team", "미배정")

            # 1-A. 근무 시간(18:00 이전)에만 실시간 진행 섹션 상단 부재 현황에 표출 (18시 이후에는 상단 자동 숨김)
            if now.hour < 18:
                leave_records.append({
                    "worker_name": w_name,
                    "worker_title": w_title,
                    "worker_team": w_team,
                    "subject": r["subject"],
                    "leave_type": l_type,
                    "start_time": st_time,
                    "end_time": ed_time,
                    "duration_hours": dur_hours,
                    "progress_pct": 100,  # 무조건 100%
                    "color_tag": r.get("color_tag", "#ec4899")
                })

            # 1-B. 휴가는 오늘 완료된 작업 섹션에 항상 100% 완료 카드로 표출 (업무량 산정은 0h 제외)
            auto_completed_rows.append({
                "msg_hash": f"OUTLOOK_LEAVE_{r.get('entry_id', '')}",
                "log_type": "휴가",
                "worker_name": w_name,
                "worker_title": w_title,
                "worker_team": w_team,
                "client_name": f"🏖️ {l_type}",
                "task_description": f"[{l_type}] {r['subject']}",
                "start_time": st_time,
                "end_time": ed_time,
                "estimated_minutes": 0,
                "actual_minutes": 0,
                "actual_hours": 0.0,
                "estimated_hours": 0.0,
                "total_hours": 0.0,
                "display_hours": dur_hours,
                "status": "COMPLETED",
                "is_outlook": True,
                "is_leave": True,
                "is_night_work": False,
                "is_weekend_work": False
            })

        # 2. 순수 카카오톡 작업 목록 추출 (아웃룩 일정과 자기 자신 매칭 원천 방지)
        # 전달받은 데이터프레임 중 is_outlook이 아닌 순수 카카오톡 보고 작업만 분리
        final_pend_df = kakao_pend_df[kakao_pend_df.get("is_outlook", False) != True].copy() if not kakao_pend_df.empty else pd.DataFrame()
        final_comp_df = today_completed_df[today_completed_df.get("is_outlook", False) != True].copy() if not today_completed_df.empty else pd.DataFrame()

        if not final_pend_df.empty:
            final_pend_df["has_both"] = False
        if not final_comp_df.empty:
            final_comp_df["has_both"] = False

        # 3. 비-휴가 일반 작업 일정 처리
        work_rows = today_out[today_out["is_leave"] == False]

        for _, r in work_rows.iterrows():
            w_name = r["worker_name"]

            st_time = r["start_time"]
            ed_time = r["end_time"]
            if pd.isna(st_time) or pd.isna(ed_time):
                continue

            st_dt = st_time.to_pydatetime() if hasattr(st_time, "to_pydatetime") else st_time
            ed_dt = ed_time.to_pydatetime() if hasattr(ed_time, "to_pydatetime") else ed_time

            # ☀️ [종일 일정 보정] 비-휴가 일반 작업 일정이 '종일(is_all_day)'인 경우 09:00~18:00 (9.0h) 표준 업무시간 강제 적용
            # (자정에 조기 완료되거나 00:00 표출 오류를 방지하고 09:00~18:00 동안 정상 진행 중 카드 표출 보장)
            is_all_day = bool(r.get("is_all_day") == True)
            if is_all_day:
                st_dt = st_dt.replace(hour=9, minute=0, second=0, microsecond=0)
                ed_dt = ed_dt.replace(hour=18, minute=0, second=0, microsecond=0)
                st_time = st_dt
                ed_time = ed_dt
                dur_hours = 9.0
            else:
                dur_hours = float(r.get("duration_hours") or 0.0)
                if dur_hours <= 0:
                    dur_hours = round(max(1800, (ed_dt - st_dt).total_seconds()) / 3600.0, 1)
                # 🛡️ 다일 일정 비정상 초과 시간 방어 (최대 9.0h)
                if (ed_dt.date() > st_dt.date()) and dur_hours > 9.0:
                    dur_hours = 9.0

            total_sec = max(1, (ed_dt - st_dt).total_seconds())
            elapsed_sec = (now - st_dt).total_seconds()

            w_title = team_info.get(w_name, {}).get("title", "")
            w_team = r.get("worker_team") or team_info.get(w_name, {}).get("team", "미배정")

            # 🏢 아웃룩 제목에서 [작업자] 제거 후 고객사명과 작업 내용을 스마트 분리 파싱
            parsed_client, parsed_desc = parse_outlook_subject_to_client_and_task(r["subject"], r.get("location", ""))

            # 🛡️ 동일 작업자가 카카오톡으로 이미 '동일 작업'을 보고했는지 정교하게 판정 (양쪽 모두 등록 시 has_both=True)
            is_dup = False
            if not final_pend_df.empty:
                for p_idx, p_row in final_pend_df.iterrows():
                    if p_row.get("worker_name") != w_name:
                        continue
                    # 🛡️ 아웃룩 출처 행은 카톡 기보고 매칭 대상에서 절대 제외 (자가 중복 방지)
                    if p_row.get("is_outlook") == True or str(p_row.get("msg_hash", "")).startswith("OUTLOOK_"):
                        continue
                    k_client = str(p_row.get("client_name", "")).strip()
                    k_desc = str(p_row.get("task_description", "")).strip()
                    matched = False
                    if k_client and k_client not in ["기타", "내부업무", "사내", "아웃룩 일정"] and (k_client == parsed_client or k_client in str(r["subject"])):
                        matched = True
                    else:
                        common_words = set(re.findall(r"[가-힣a-zA-Z0-9]{2,}", str(r["subject"]))) & set(re.findall(r"[가-힣a-zA-Z0-9]{2,}", f"{k_client} {k_desc}"))
                        meaningful_common = {w for w in common_words if w not in ["작업", "회의", "미팅", "지원", "점검", "수석", "팀장", "기술본부", "기술", "고객사", "프로젝트", "업무", "일정", "완료", "진행", "1팀", "2팀", "3팀"]}
                        if meaningful_common:
                            matched = True
                        else:
                            k_st = p_row.get("start_time")
                            if pd.notna(k_st):
                                k_st_dt = k_st.to_pydatetime() if hasattr(k_st, "to_pydatetime") else k_st
                                if abs((st_dt - k_st_dt).total_seconds()) < 1800 and (k_client == parsed_client or not parsed_client):
                                    matched = True

                    if matched:
                        final_pend_df.at[p_idx, "has_both"] = True
                        if r.get("schedule_type") == "교육":
                            final_pend_df.at[p_idx, "log_type"] = "교육"
                        is_dup = True
                        break

            if not is_dup and not final_comp_df.empty:
                for c_idx, c_row in final_comp_df.iterrows():
                    if c_row.get("worker_name") != w_name:
                        continue
                    # 🛡️ 아웃룩 출처 행은 카톡 기보고 매칭 대상에서 절대 제외 (자가 중복 방지)
                    if c_row.get("is_outlook") == True or str(c_row.get("msg_hash", "")).startswith("OUTLOOK_"):
                        continue
                    k_client = str(c_row.get("client_name", "")).strip()
                    k_desc = str(c_row.get("task_description", "")).strip()
                    matched = False
                    if k_client and k_client not in ["기타", "내부업무", "사내", "아웃룩 일정"] and (k_client == parsed_client or k_client in str(r["subject"])):
                        matched = True
                    else:
                        common_words = set(re.findall(r"[가-힣a-zA-Z0-9]{2,}", str(r["subject"]))) & set(re.findall(r"[가-힣a-zA-Z0-9]{2,}", f"{k_client} {k_desc}"))
                        meaningful_common = {w for w in common_words if w not in ["작업", "회의", "미팅", "지원", "점검", "수석", "팀장", "기술본부", "기술", "고객사", "프로젝트", "업무", "일정", "완료", "진행", "1팀", "2팀", "3팀"]}
                        if meaningful_common:
                            matched = True
                        else:
                            k_st = c_row.get("start_time")
                            if pd.notna(k_st):
                                k_st_dt = k_st.to_pydatetime() if hasattr(k_st, "to_pydatetime") else k_st
                                if abs((st_dt - k_st_dt).total_seconds()) < 1800 and (k_client == parsed_client or not parsed_client):
                                    matched = True

                    if matched:
                        final_comp_df.at[c_idx, "has_both"] = True
                        if r.get("schedule_type") == "교육":
                            final_comp_df.at[c_idx, "log_type"] = "교육"
                        is_dup = True
                        break

            if is_dup:
                continue

            # A. 현재 시간이 종료 시각 이후 -> 100% 도달 -> 자동 완료 전환
            if now >= ed_dt:
                auto_completed_rows.append({
                    "msg_hash": f"OUTLOOK_COMP_{r.get('entry_id', '')}",
                    "log_type": "작업",
                    "worker_name": w_name,
                    "worker_title": w_title,
                    "worker_team": w_team,
                    "client_name": parsed_client,
                    "task_description": f"[📅 일정완료] {parsed_desc}",
                    "start_time": st_time,
                    "end_time": ed_time,
                    "estimated_minutes": int(dur_hours * 60),
                    "actual_minutes": int(dur_hours * 60),
                    "actual_hours": dur_hours,
                    "total_hours": dur_hours,
                    "status": "COMPLETED",
                    "is_outlook": True,
                    "is_all_day": is_all_day,
                    "has_both": False,
                    "is_night_work": False,
                    "is_weekend_work": False
                })
            # B. 시작 30분 전부터 종료 이전 -> 실시간 진행 중 작업 승격 (시작 전에는 프로그레스 바 0%)
            elif now >= (st_dt - timedelta(minutes=30)):
                if now >= st_dt:
                    pct = min(99, max(5, int((elapsed_sec / total_sec) * 100)))
                    actual_mins = int((elapsed_sec / 60))
                else:
                    pct = 0
                    actual_mins = 0
                promoted_pend_rows.append({
                    "msg_hash": f"OUTLOOK_PEND_{r.get('entry_id', '')}",
                    "log_type": "작업",
                    "worker_name": w_name,
                    "worker_title": w_title,
                    "worker_team": w_team,
                    "client_name": parsed_client,
                    "task_description": f"[📅 아웃룩] {parsed_desc}",
                    "start_time": st_time,
                    "end_time": ed_time,
                    "estimated_minutes": int(dur_hours * 60),
                    "actual_minutes": actual_mins,
                    "total_hours": dur_hours,
                    "status": "PENDING",
                    "is_outlook": True,
                    "is_all_day": is_all_day,
                    "has_both": False,
                    "outlook_progress_pct": pct,
                    "is_night_work": False,
                    "is_weekend_work": False
                })

        if promoted_pend_rows:
            prom_df = pd.DataFrame(promoted_pend_rows)
            final_pend_df = pd.concat([final_pend_df, prom_df], ignore_index=True)

        auto_comp_df = pd.DataFrame(auto_completed_rows) if auto_completed_rows else pd.DataFrame()

        return final_pend_df, final_comp_df, auto_comp_df, leave_records

    @classmethod
    def combine_all_work_logs(
        cls,
        kakao_df: pd.DataFrame,
        outlook_df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        📋 대시보드 전체(작업 기록 원장, 통계 분석, 주간/월간 업무량, LIVE 관제)에서
        카카오톡 기록과 아웃룩 전체 일정(연차, 회의, 프로젝트 지원)을 완벽하게 일원화하여 병합합니다.
        
        - 연차/휴가/반차: 업무량 산정(actual_hours)에서 100% 완전 제외 (0.0h), 카드 표출용(display_hours) 보존
        - 아웃룩 실제 작업/회의: 실제 공수(actual_hours)에 정상 합산
        - 카카오톡 기보고 동일 작업: 지능형 중복 배제 (카카오톡 최우선 존중)
        """
        now = get_current_kst_time().replace(tzinfo=None)
        team_info = TeamService.get_team_members_info()
        team_mappings = TeamService.get_team_mappings()
        title_mappings = TeamService.get_title_mappings()

        if outlook_df is None or outlook_df.empty:
            try:
                if hasattr(db_manager, "fetch_outlook_schedules"):
                    outlook_df = db_manager.fetch_outlook_schedules()
                elif fetch_outlook_schedules is not None:
                    outlook_df = fetch_outlook_schedules()
                else:
                    import importlib
                    import src.database.supabase_client as sc
                    importlib.reload(sc)
                    outlook_df = sc.db_manager.fetch_outlook_schedules()
            except Exception:
                outlook_df = pd.DataFrame()

        # 1. 카카오톡 작업 목록 (작업자별) 매핑
        kakao_tasks_by_worker = {}
        if not kakao_df.empty and "worker_name" in kakao_df.columns:
            for _, k_r in kakao_df.iterrows():
                wn = k_r.get("worker_name")
                if wn:
                    kakao_tasks_by_worker.setdefault(wn, []).append(k_r.to_dict())

        outlook_converted_rows = []

        if not outlook_df.empty and "start_time" in outlook_df.columns:
            out_copy = outlook_df.copy()
            if not pd.api.types.is_datetime64_any_dtype(out_copy["start_time"]):
                out_copy["start_time"] = pd.to_datetime(out_copy["start_time"].astype(str).str.replace("T", " "), errors="coerce")
            if not pd.api.types.is_datetime64_any_dtype(out_copy["end_time"]):
                out_copy["end_time"] = pd.to_datetime(out_copy["end_time"].astype(str).str.replace("T", " "), errors="coerce")

            for _, r in out_copy.iterrows():
                w_name = r.get("worker_name")
                if not w_name:
                    continue

                st_time = r["start_time"]
                ed_time = r["end_time"]
                if pd.isna(st_time) or pd.isna(ed_time):
                    continue

                st_dt = st_time.to_pydatetime() if hasattr(st_time, "to_pydatetime") else st_time
                ed_dt = ed_time.to_pydatetime() if hasattr(ed_time, "to_pydatetime") else ed_time

                # 🔮 미래 일정 수집 제외: 오늘 이후(st_dt.date() > now.date())의 미래 일정은
                # 아직 근무하지 않은 미래시이므로 작업 원장 및 대시보드 통계(work_logs)에 수집·산정하지 않습니다.
                # (※ 미래 캘린더 전체 일정표는 outlook_calendar_widget에서 자체적으로 언제든 확인 가능)
                if st_dt.date() > now.date():
                    continue

                is_leave = bool(r.get("is_leave", False))
                is_all_day = bool(r.get("is_all_day", False))
                l_type = r.get("leave_type") or "연차"

                if not is_leave and is_all_day:
                    st_dt = st_dt.replace(hour=9, minute=0, second=0, microsecond=0)
                    ed_dt = ed_dt.replace(hour=18, minute=0, second=0, microsecond=0)
                    st_time = st_dt
                    ed_time = ed_dt
                    dur_hours = 9.0
                elif is_leave:
                    dur_hours = 4.5 if ("반차" in str(l_type) or "반일" in str(l_type)) else 9.0
                else:
                    raw_dur = r.get("duration_hours")
                    if raw_dur is not None and float(raw_dur) > 0:
                        dur_hours = float(raw_dur)
                    else:
                        total_sec = max(1800, (ed_dt - st_dt).total_seconds())
                        dur_hours = round(total_sec / 3600.0, 1)

                    # 🛡️ [다일 일정 초과 시간 방어 및 당일 윈도우 보정]
                    # 날짜가 다른 다일 일정이 분할되지 않고 81h 등으로 남아있는 경우,
                    # 예정 및 실제 공수는 하루 정규 근무 시간인 9.0h로 캡 적용하고
                    # 당일 진행 중 표출 시 경과시간이 35h 등으로 튀지 않도록 오늘 09:00~18:00으로 윈도우 보정
                    if ed_dt.date() > st_dt.date():
                        dur_hours = min(dur_hours, 9.0)
                        if st_dt.date() <= now.date() <= ed_dt.date():
                            today_d = now.date()
                            st_dt = datetime.combine(today_d, st_dt.time() if st_dt.date() == today_d else datetime.min.time().replace(hour=9))
                            ed_dt = datetime.combine(today_d, ed_dt.time() if ed_dt.date() == today_d else datetime.min.time().replace(hour=18))
                            st_time = st_dt
                            ed_time = ed_dt

                w_title = title_mappings.get(w_name) or team_info.get(w_name, {}).get("title", "")
                w_team = team_mappings.get(w_name) or r.get("worker_team") or team_info.get(w_name, {}).get("team", "미배정")
                entry_id = str(r.get("entry_id") or "")
                subj = str(r.get("subject") or "")

                if is_leave:
                    # 🏖️ 사용자 확정 원칙: 연차/휴가/반차는 업무량 산정에서 완전 제외(0h), 카드 표출 전용
                    row_dict = {
                        "msg_hash": f"OUTLOOK_LEAVE_{entry_id}",
                        "log_type": "휴가",
                        "worker_name": w_name,
                        "worker_title": w_title,
                        "worker_team": w_team,
                        "client_name": f"🏖️ {l_type}",
                        "task_description": f"[{l_type}] {subj}",
                        "start_time": st_time,
                        "end_time": ed_time,
                        "estimated_minutes": 0,
                        "actual_minutes": 0,
                        "actual_hours": 0.0,       # 🌟 업무량 산정 완전 제외 (0.0h)
                        "estimated_hours": 0.0,
                        "total_hours": 0.0,
                        "display_hours": dur_hours, # 🌟 카드 뱃지 표출용 (9.0h / 4.5h)
                        "status": "SCHEDULED" if st_dt > now else "COMPLETED",
                        "is_outlook": True,
                        "is_leave": True,
                        "is_night_work": False,
                        "is_weekend_work": False
                    }
                    outlook_converted_rows.append(row_dict)
                else:
                    # 🏢 비-휴가 일반 작업 일정
                    parsed_client, parsed_desc = parse_outlook_subject_to_client_and_task(subj, r.get("location", ""))

                    # 중복 검사: 동일 날짜의 카카오톡에 이미 보고된 동일 작업인지 확인
                    worker_k_tasks = kakao_tasks_by_worker.get(w_name, [])
                    is_dup = False
                    for k in worker_k_tasks:
                        k_st = k.get("start_time")
                        if pd.isna(k_st):
                            continue
                        k_st_dt = k_st.to_pydatetime() if hasattr(k_st, "to_pydatetime") else k_st
                        # 🌟 필수: 같은 날짜의 카카오톡 작업만 중복 비교 대상으로 한정 (과거 이력 때문에 당일 아웃룩이 누락되는 현상 원천 방지)
                        if st_dt.date() != k_st_dt.date():
                            continue

                        k_client = str(k.get("client_name", "")).strip()
                        k_desc = str(k.get("task_description", "")).strip()

                        if k_client and k_client not in ["기타", "내부업무", "사내", "아웃룩 일정"] and (k_client == parsed_client or k_client in subj):
                            is_dup = True
                            break
                        common_words = set(re.findall(r"[가-힣a-zA-Z0-9]{2,}", subj)) & set(re.findall(r"[가-힣a-zA-Z0-9]{2,}", f"{k_client} {k_desc}"))
                        meaningful_common = {w for w in common_words if w not in ["작업", "회의", "미팅", "지원", "점검", "수석", "팀장", "기술본부", "기술", "고객사", "프로젝트", "업무", "일정", "완료", "진행", "1팀", "2팀", "3팀"]}
                        if meaningful_common:
                            is_dup = True
                            break
                        if abs((st_dt - k_st_dt).total_seconds()) < 1800 and (k_client == parsed_client or not parsed_client):
                            is_dup = True
                            break
                    if is_dup:
                        continue

                    sched_type = r.get("schedule_type") or "작업"
                    log_type = "회의" if sched_type == "회의" else ("교육" if sched_type == "교육" else "작업")

                    is_completed = (now >= ed_dt)
                    is_pending = (now >= (st_dt - timedelta(minutes=30)) and now < ed_dt)
                    if is_completed:
                        status = "COMPLETED"
                        act_h = dur_hours
                        act_m = int(dur_hours * 60)
                    elif is_pending:
                        status = "PENDING"
                        if now >= st_dt:
                            elapsed_sec = max(0, (now - st_dt).total_seconds())
                            act_h = round(elapsed_sec / 3600.0, 1)
                            act_m = int(elapsed_sec / 60)
                        else:
                            act_h = 0.0
                            act_m = 0
                    else:
                        # 🔮 미래 예정 일정: 미래시는 아직 근무하지 않았으므로 0.0h 부여
                        status = "SCHEDULED"
                        act_h = 0.0
                        act_m = 0

                    task_desc = parsed_desc

                    row_dict = {
                        "msg_hash": f"OUTLOOK_WORK_{entry_id}",
                        "log_type": log_type,
                        "worker_name": w_name,
                        "worker_title": w_title,
                        "worker_team": w_team,
                        "client_name": parsed_client,
                        "task_description": task_desc,
                        "start_time": st_time,
                        "end_time": ed_time if is_completed else None,  # 🌟 18시 종료 이전(진행 중)에는 완료보고시각 None 유지
                        "scheduled_end_time": ed_time,
                        "estimated_minutes": int(dur_hours * 60),
                        "actual_minutes": act_m,
                        "actual_hours": act_h,       # 🌟 미래시는 0.0h, 완료는 dur_hours, 진행은 경과시간
                        "estimated_hours": dur_hours,
                        "total_hours": dur_hours,
                        "display_hours": dur_hours,  # 🌟 캘린더/카드 표시용
                        "status": status,
                        "is_outlook": True,
                        "is_leave": False,
                        "is_night_work": False,
                        "is_weekend_work": False
                    }
                    outlook_converted_rows.append(row_dict)

        if outlook_converted_rows:
            out_df_converted = pd.DataFrame(outlook_converted_rows)
            combined_df = pd.concat([kakao_df, out_df_converted], ignore_index=True)
        else:
            combined_df = kakao_df.copy()

        # 🎓 교육 작업 분류 보장: task_description이나 client_name에 교육/실습/세미나가 포함되어 있으면 log_type을 '교육'으로 보정
        # (주 40h/52h 법정 근로시간 집계 시 자동 제외, 진행/완료 카드에는 정상 표출)
        if not combined_df.empty and "task_description" in combined_df.columns:
            edu_mask = combined_df["task_description"].astype(str).str.contains("교육|실습|세미나|학습", regex=True) | \
                       combined_df.get("client_name", pd.Series("", index=combined_df.index)).astype(str).str.contains("교육|협회|아카데미", regex=True)
            if "is_leave" in combined_df.columns:
                edu_mask = edu_mask & (~combined_df["is_leave"].fillna(False).astype(bool))
            combined_df.loc[edu_mask, "log_type"] = "교육"

        # 팀 및 직급 매핑 안전 보장
        if team_mappings and "worker_name" in combined_df.columns:
            combined_df["worker_team"] = combined_df["worker_name"].map(team_mappings).fillna(combined_df.get("worker_team", "")).fillna("미배정")
        if title_mappings and "worker_name" in combined_df.columns:
            combined_df["worker_title"] = combined_df["worker_name"].map(title_mappings).fillna(combined_df.get("worker_title", ""))

        return combined_df
