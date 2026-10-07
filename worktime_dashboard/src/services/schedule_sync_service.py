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
from src.parser.reply_matcher import check_is_night_work

class ScheduleSyncService:
    """
    아웃룩 일정과 카카오톡 실시간 작업 동기화 및 미래시 승격 서비스
    1. 카톡 미보고 작업 -> 일정표 시간대 도달 시 실시간 진행 작업으로 자동 승격
    2. 100% 진행률 도달 시 자동으로 완료(COMPLETED) 작업으로 전환
    3. 휴가/연차/반차 -> 실시간 진행 영역에 무조건 100%로 상시 표출
    4. 카톡 보고와 아웃룩 일정이 동일 업무일 경우 지능적 병합 (중복 제거)
    """

    @classmethod
    def _extract_client_core_keywords(cls, text: str) -> set:
        """
        고객사명이나 작업 제목에서 은행, 증권, 상주, 지원 등 부가어를 뗀
        순수 브랜드/고객사 핵심 키워드들을 추출 (예: '수협은행' -> {'수협'}, '수협상주지원' -> {'수협', '상주'})
        """
        if not text:
            return set()
        clean = re.sub(r"[\[\]\(\)\/,\-_~]", " ", str(text))
        stopwords = {
            "작업", "회의", "미팅", "지원", "점검", "수석", "팀장", "기술본부", "기술", "고객사", 
            "프로젝트", "업무", "일정", "완료", "진행", "1팀", "2팀", "3팀", "기타", "사내", "내부업무", 
            "대체근무", "근무", "일차", "상주대체근무", "상주지원", "아웃룩", "오전", "오후"
        }
        words = set()
        for token in clean.split():
            token = token.strip()
            if len(token) < 2 or token in stopwords:
                continue
            # 주요 고객사 핵심 패턴 축약 (예: 수협은행 -> 수협, 국민은행 -> 국민, 신한은행 -> 신한, 등)
            for prefix in ["수협", "국민", "신한", "하나", "농협", "기업", "신협", "대구", "IM", "iM", "KDB", "IBK", "SBI", "BGF", "AIG", "금호", "가온", "애경", "명인", "상상인", "한전"]:
                if token.startswith(prefix) or prefix in token:
                    words.add(prefix.upper())
            # 일반 2글자 이상 명사 추가
            sub_clean = re.sub(r"(?:은행|증권|생명|화재|캐피탈|저축은행|카드|센터|지점|본점|연구소|공장|공전소|사무소|IT센터|영업부|사업처)$", "", token)
            if len(sub_clean) >= 2 and sub_clean not in stopwords:
                words.add(sub_clean)
            elif len(token) >= 2 and token not in stopwords:
                words.add(token)
        return words

    @classmethod
    def is_same_task_match(
        cls,
        k_client: str,
        k_desc: str,
        k_st_dt: Any,
        parsed_client: str,
        parsed_desc: str,
        subject: str,
        out_st_dt: Any
    ) -> bool:
        """
        카카오톡 보고 작업과 아웃룩 일정이 동일한 업무인지 지능적으로 판정하는 통합 엔진
        """
        k_c = (k_client or "").strip()
        p_c = (parsed_client or "").strip()
        subj = (subject or "").strip()
        k_d = (k_desc or "").strip()

        invalid_clients = ["기타", "내부업무", "사내", "아웃룩 일정", ""]

        # 1. 고객사명 완전 일치 또는 상호 포함 (유효 고객사인 경우)
        if k_c and k_c not in invalid_clients:
            if k_c == p_c:
                return True
            if k_c in subj or k_c in p_c or (p_c not in invalid_clients and p_c in k_c):
                return True

        # 2. 고객사 핵심 키워드(Core Alias) 추출 및 충돌 가드
        k_core = cls._extract_client_core_keywords(f"{k_c} {k_d}")
        out_core = cls._extract_client_core_keywords(f"{p_c} {subj}")
        common_core = k_core & out_core

        # 🛡️ 명시적 고객사 충돌 방어: 둘 다 명확한 고객사인데 핵심어가 완전히 상이하면 절대 오매칭 금지! (예: 수협은행 vs 하나은행)
        if (k_c and k_c not in invalid_clients) and (p_c and p_c not in invalid_clients):
            if k_core and out_core and not common_core:
                return False

        if common_core:
            # 같은 날짜이고 시간차가 3시간 이내이면 동일 업무 확정
            if hasattr(k_st_dt, "date") and hasattr(out_st_dt, "date") and k_st_dt.date() == out_st_dt.date():
                if abs((out_st_dt - k_st_dt).total_seconds()) <= 10800:
                    return True

        # 3. 띄어쓰기 무시 N-gram 및 부분 문자열 매칭 (일반 업종/직책어 제외)
        clean_k = re.sub(r"[\s\-_\[\]\(\)\/]", "", f"{k_c}{k_d}")
        clean_out = re.sub(r"[\s\-_\[\]\(\)\/]", "", f"{p_c}{subj}")
        general_words = {
            "은행", "증권", "생명", "화재", "카드", "센터", "공장", "연구소", "작업", "회의", 
            "지원", "점검", "수석", "팀장", "기술", "일정", "대체", "정기", "상주", "근무"
        }
        if len(clean_k) >= 2 and len(clean_out) >= 2:
            overlap_count = 0
            for i in range(len(clean_out) - 1):
                gram = clean_out[i:i+2]
                if gram in clean_k and gram not in general_words:
                    overlap_count += 1
            if overlap_count >= 2:
                if hasattr(k_st_dt, "date") and hasattr(out_st_dt, "date") and k_st_dt.date() == out_st_dt.date():
                    return True

        # 4. 동일 시간대(±30분 이내) 단일 작업 가드 (동일 작업자 1인 1작업 룰)
        if hasattr(k_st_dt, "date") and hasattr(out_st_dt, "date") and k_st_dt.date() == out_st_dt.date():
            time_diff_sec = abs((out_st_dt - k_st_dt).total_seconds())
            if time_diff_sec < 1800:
                # 시작 시간이 30분 이내이고, 핵심어가 1개라도 일치하거나 둘 중 하나가 기타/사내이면 매칭
                if common_core or (k_c == p_c) or (not p_c or p_c in invalid_clients):
                    return True

        return False

    @classmethod
    def get_synced_live_tasks(
        cls,
        kakao_pend_df: pd.DataFrame,
        today_completed_df: pd.DataFrame,
        kakao_sched_df: Optional[pd.DataFrame] = None,
        outlook_df: Optional[pd.DataFrame] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, List[Dict[str, Any]]]:
        """
        카카오톡 진행 작업과 아웃룩 일정을 병합하여
        1) 최종 실시간 진행 작업 데이터프레임 (final_pend_df)
        2) 오늘 예정 일정 데이터프레임 (final_sched_df)
        3) 카카오톡 완료 작업 데이터프레임 (final_comp_df)
        4) 아웃룩에서 100% 완료로 승격된 작업 데이터프레임 (auto_comp_df)
        5) 오늘 휴가/연차/반차 목록 (leave_records)
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
            empty_sched = kakao_sched_df if (kakao_sched_df is not None and not kakao_sched_df.empty) else pd.DataFrame()
            return kakao_pend_df, empty_sched, today_completed_df, pd.DataFrame(), []

        # 오늘 아웃룩 일정 필터링
        today_out = outlook_df.copy()
        if not pd.api.types.is_datetime64_any_dtype(today_out["start_time"]):
            today_out["start_time"] = pd.to_datetime(today_out["start_time"].astype(str).str.replace("T", " "), errors="coerce")
        if not pd.api.types.is_datetime64_any_dtype(today_out["end_time"]):
            today_out["end_time"] = pd.to_datetime(today_out["end_time"].astype(str).str.replace("T", " "), errors="coerce")

        today_out = today_out[today_out["start_time"].dt.strftime("%Y-%m-%d") == today_str]
        today_out = today_out.drop_duplicates(subset=["worker_name", "subject", "start_time"])

        promoted_pend_rows = []
        upcoming_rows = []
        auto_completed_rows = []
        team_info = TeamService.get_team_members_info()

        # 1. 휴가/연차/반차 추출 (B안 정책: 종료 시각 이전에는 상단 실시간 부재 현황, 종료 후에는 오늘 완료된 작업으로 즉시 이동)
        leave_records = []
        leave_kws = ["연차", "반차", "오전반차", "오후반차", "휴가", "공가", "보상휴가", "병가", "병원", "진료", "건강검진", "외출", "조퇴"]
        leave_mask = (today_out["is_leave"] == True) | today_out["subject"].astype(str).apply(lambda s: any(kw in s for kw in leave_kws))
        leave_rows = today_out[leave_mask]

        # 🛡️ 동일 작업자 중복/겹침 휴가 일정 사전 통합 (예: '[김시우] 병원 진료' vs '[김시우] 오전 반차 (병원 진료)')
        deduped_leave_items = []
        for _, r in leave_rows.iterrows():
            w_name = r["worker_name"]
            st_time = r["start_time"]
            ed_time = r["end_time"]
            st_dt = st_time.to_pydatetime() if hasattr(st_time, "to_pydatetime") else st_time
            ed_dt = ed_time.to_pydatetime() if hasattr(ed_time, "to_pydatetime") else ed_time
            if hasattr(st_dt, "tzinfo") and st_dt.tzinfo is not None:
                st_dt = st_dt.replace(tzinfo=None)
            if hasattr(ed_dt, "tzinfo") and ed_dt.tzinfo is not None:
                ed_dt = ed_dt.replace(tzinfo=None)

            is_merged = False
            for idx, existing in enumerate(deduped_leave_items):
                if existing["worker_name"] == w_name:
                    ex_st_dt = existing["st_dt"]
                    ex_ed_dt = existing["ed_dt"]
                    overlap = False
                    if st_dt and ed_dt and ex_st_dt and ex_ed_dt:
                        overlap = max(st_dt, ex_st_dt) < min(ed_dt, ex_ed_dt)
                    else:
                        overlap = True
                    if overlap:
                        subj_new = str(r.get("subject", ""))
                        subj_ex = str(existing["r"].get("subject", ""))
                        has_explicit_new = any(k in subj_new for k in ["연차", "반차", "휴가", "공가", "오전반차", "오후반차"])
                        has_explicit_ex = any(k in subj_ex for k in ["연차", "반차", "휴가", "공가", "오전반차", "오후반차"])
                        if (has_explicit_new and not has_explicit_ex) or (has_explicit_new == has_explicit_ex and len(subj_new) > len(subj_ex)):
                            deduped_leave_items[idx] = {"r": r, "worker_name": w_name, "st_dt": st_dt, "ed_dt": ed_dt}
                        is_merged = True
                        break
            if not is_merged:
                deduped_leave_items.append({"r": r, "worker_name": w_name, "st_dt": st_dt, "ed_dt": ed_dt})

        for item in deduped_leave_items:
            r = item["r"]
            w_name = item["worker_name"]
            st_time = r["start_time"]
            ed_time = r["end_time"]
            st_dt = item["st_dt"]
            ed_dt = item["ed_dt"]

            l_type = r.get("leave_type") or "연차"
            if "반차" in str(l_type) or "반일" in str(l_type):
                dur_hours = 4.5
            elif "연차" in str(l_type) or "휴가" in str(l_type):
                dur_hours = 9.0
            else:
                dur_hours = float(r.get("duration_hours") or 9.0)
            w_title = team_info.get(w_name, {}).get("title", "")
            w_team = r.get("worker_team") or team_info.get(w_name, {}).get("team", "미배정")

            # 🌟 [B안: 종료 즉시 퇴장 정책 & 연차/반차 완료 일정 표출]
            # - 종일 연차: 퇴근 시간(18:00)까지 상단 부재 현황판 유지 + 오늘 완료된 작업(하단)에도 연차 카드로 표출
            # - 반차(오전/오후): 반차 진행 중에는 상단 부재 현황판에 표출, 종료 시각(ed_dt) 경과 후 상단에서 퇴장하고 하단 완료 일정에 표출
            is_all_day = bool(r.get("is_all_day") == True)
            is_full_leave = is_all_day or ("연차" in str(l_type) and "반차" not in str(l_type) and "반일" not in str(l_type))

            if is_full_leave:
                leave_end_cutoff = ed_dt.replace(hour=18, minute=0, second=0, microsecond=0) if (pd.notna(ed_dt) and ed_dt.hour < 18) else ed_dt
            else:
                leave_end_cutoff = ed_dt

            is_leave_ended = (pd.notna(leave_end_cutoff) and now >= leave_end_cutoff) or (now.hour >= 18)

            if not is_leave_ended:
                # 1-A. 휴가/반차 진행 중: 상단 실시간 부재 현황판에 표출
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

            # 1-B. 하단 오늘 완료된 작업 섹션:
            # - 반차: 종료 시각(ed_dt) 이후 완료 일정에 표출
            # - 연차: 사용자 요청(연차도 완료 일정에 표시)에 따라 당일 완료 일정에 항상 표출 (업무량 산정은 0h 제외)
            if is_leave_ended or is_full_leave:
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
        if not kakao_pend_df.empty:
            if "is_outlook" in kakao_pend_df.columns:
                final_pend_df = kakao_pend_df[kakao_pend_df["is_outlook"] != True].copy()
            else:
                final_pend_df = kakao_pend_df.copy()
            final_pend_df["has_both"] = False
        else:
            final_pend_df = pd.DataFrame()

        if not today_completed_df.empty:
            if "is_outlook" in today_completed_df.columns:
                final_comp_df = today_completed_df[today_completed_df["is_outlook"] != True].copy()
            else:
                final_comp_df = today_completed_df.copy()
            final_comp_df["has_both"] = False
        else:
            final_comp_df = pd.DataFrame()

        # 3. 비-휴가 일반 작업 일정 처리 (휴가 일정 원천 배제)
        work_rows = today_out[~leave_mask]

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

            # 🛡️ 1. 휴가/개인용무 키워드 방어 (작업이 아니므로 실시간 진행/예정 작업 승격 배제)
            non_work_keywords = ["병원", "진료", "건강검진", "휴가", "연차", "반차", "공가", "병가", "외출", "조퇴", "개인용무", "개인사정"]
            subj_raw = str(r.get("subject", "")).strip()
            if any(kw in subj_raw for kw in non_work_keywords) or any(kw in str(parsed_client) for kw in non_work_keywords):
                continue

            # 🛡️ 2. 해당 작업자가 동일 시간대에 이미 휴가(leave_records)로 등록되어 있는 경우
            # (휴가 중인 시간대에 등록된 아웃룩 일정은 실시간 진행/예정 작업 승격 원천 차단)
            is_worker_on_leave = False
            for l_rec in leave_records:
                if l_rec.get("worker_name") == w_name:
                    l_st = l_rec.get("start_time")
                    l_ed = l_rec.get("end_time")
                    l_st_dt = l_st.to_pydatetime() if (pd.notna(l_st) and hasattr(l_st, "to_pydatetime")) else l_st
                    l_ed_dt = l_ed.to_pydatetime() if (pd.notna(l_ed) and hasattr(l_ed, "to_pydatetime")) else l_ed
                    # 시간대 겹침 확인
                    if max(st_dt, l_st_dt) < min(ed_dt, l_ed_dt):
                        is_worker_on_leave = True
                        break
            if is_worker_on_leave:
                continue

            # 🛡️ 동일 작업자가 카카오톡으로 이미 '동일 작업'을 보고했는지 지능적으로 판정 (양쪽 모두 등록 시 has_both=True)
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
                    k_st = p_row.get("start_time")
                    k_st_dt = k_st.to_pydatetime() if (pd.notna(k_st) and hasattr(k_st, "to_pydatetime")) else k_st

                    if cls.is_same_task_match(k_client, k_desc, k_st_dt, parsed_client, parsed_desc, r["subject"], st_dt):
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
                    k_st = c_row.get("start_time")
                    k_st_dt = k_st.to_pydatetime() if (pd.notna(k_st) and hasattr(k_st, "to_pydatetime")) else k_st

                    if cls.is_same_task_match(k_client, k_desc, k_st_dt, parsed_client, parsed_desc, r["subject"], st_dt):
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
            # C. 시작 30분 전 이전 -> 오늘 예정 일정 (SCHEDULED)
            else:
                is_night = check_is_night_work(st_dt, ed_dt, parsed_desc, int(dur_hours * 60))
                upcoming_rows.append({
                    "msg_hash": f"OUTLOOK_SCHED_{r.get('entry_id', '')}",
                    "log_type": "작업",
                    "worker_name": w_name,
                    "worker_title": w_title,
                    "worker_team": w_team,
                    "client_name": parsed_client,
                    "task_description": f"[📅 예정] {parsed_desc}",
                    "start_time": st_time,
                    "end_time": ed_time,
                    "scheduled_start_time": st_time,
                    "scheduled_end_time": ed_time,
                    "estimated_minutes": int(dur_hours * 60),
                    "actual_minutes": 0,
                    "actual_hours": 0.0,
                    "estimated_hours": dur_hours,
                    "total_hours": dur_hours,
                    "display_hours": dur_hours,
                    "status": "SCHEDULED",
                    "is_outlook": True,
                    "is_all_day": is_all_day,
                    "has_both": False,
                    "is_night_work": is_night,
                    "is_weekend_work": False
                })

        if promoted_pend_rows:
            prom_df = pd.DataFrame(promoted_pend_rows)
            final_pend_df = pd.concat([final_pend_df, prom_df], ignore_index=True)

        if kakao_sched_df is not None and not kakao_sched_df.empty:
            if "is_outlook" in kakao_sched_df.columns:
                final_sched_df = kakao_sched_df[kakao_sched_df["is_outlook"] != True].copy()
            else:
                final_sched_df = kakao_sched_df.copy()
            final_sched_df["has_both"] = False
        else:
            final_sched_df = pd.DataFrame()

        if upcoming_rows:
            up_df = pd.DataFrame(upcoming_rows)
            final_sched_df = pd.concat([final_sched_df, up_df], ignore_index=True)
            final_sched_df = final_sched_df.drop_duplicates(subset=["worker_name", "start_time", "task_description"], keep="first")

        auto_comp_df = pd.DataFrame(auto_completed_rows) if auto_completed_rows else pd.DataFrame()

        return final_pend_df, final_sched_df, final_comp_df, auto_comp_df, leave_records

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

                subj_str = str(r.get("subject", ""))
                leave_kws = ["연차", "반차", "오전반차", "오후반차", "휴가", "공가", "보상휴가", "병가", "병원", "진료", "건강검진", "외출", "조퇴"]
                has_leave_kw = any(kw in subj_str for kw in leave_kws)
                is_leave = bool(r.get("is_leave", False)) or has_leave_kw
                is_all_day = bool(r.get("is_all_day", False))
                l_type = r.get("leave_type")
                if not l_type or str(l_type).strip() == "" or l_type == "기타":
                    l_type = "반차" if any(kw in subj_str for kw in ["반차", "오전반차", "오후반차", "병원", "진료", "외출", "조퇴"]) else "연차"

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

                st_dt_obj = st_time.to_pydatetime() if hasattr(st_time, "to_pydatetime") else st_time
                date_str_val = st_dt_obj.strftime("%Y-%m-%d") if hasattr(st_dt_obj, "strftime") else ""
                month_str_val = st_dt_obj.strftime("%Y-%m") if hasattr(st_dt_obj, "strftime") else ""
                week_str_val = f"{st_dt_obj.isocalendar()[0]}-{st_dt_obj.isocalendar()[1]}주" if hasattr(st_dt_obj, "isocalendar") else ""
                try:
                    from src.dashboard.common.ui_helpers import get_month_clamped_week_label
                    week_label_val = get_month_clamped_week_label(st_dt_obj)
                except Exception:
                    week_label_val = f"{month_str_val} 주차"

                if is_leave:
                    # 🏖️ 당일(오늘) 휴가는 종료 전(종일연차는 18:00 전)에는 실시간 부재(SCHEDULED),
                    # 반차/휴가 종료 시각 이후 또는 과거 날짜의 휴가는 COMPLETED 부여
                    is_leave_ended_comb = False
                    if st_dt.date() == now.date():
                        is_all_day_l = bool(r.get("is_all_day") == True)
                        if is_all_day_l or ("연차" in str(l_type) and "반차" not in str(l_type) and "반일" not in str(l_type)):
                            cutoff_l = ed_dt.replace(hour=18, minute=0, second=0, microsecond=0) if (pd.notna(ed_dt) and ed_dt.hour < 18) else ed_dt
                        else:
                            cutoff_l = ed_dt
                        is_leave_ended_comb = (pd.notna(cutoff_l) and now >= cutoff_l) or (now.hour >= 18)
                    elif st_dt > now:
                        is_leave_ended_comb = False
                    else:
                        is_leave_ended_comb = True

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
                        "display_hours": dur_hours,
                        "date_str": date_str_val,
                        "month_str": month_str_val,
                        "week_label": week_label_val,
                        "week_str": week_str_val,
                        "status": "COMPLETED" if is_leave_ended_comb else "SCHEDULED",
                        "is_outlook": True,
                        "is_leave": True,
                        "is_night_work": False,
                        "is_weekend_work": False
                    }
                    outlook_converted_rows.append(row_dict)
                else:
                    # 🏢 비-휴가 일반 작업 일정
                    parsed_client, parsed_desc = parse_outlook_subject_to_client_and_task(subj, r.get("location", ""))

                    # 중복 검사: 동일 날짜의 카카오톡에 이미 보고된 동일 작업인지 지능적 확인
                    worker_k_tasks = kakao_tasks_by_worker.get(w_name, [])
                    is_dup = False
                    for k in worker_k_tasks:
                        k_st = k.get("start_time")
                        if pd.isna(k_st):
                            continue
                        k_st_dt = k_st.to_pydatetime() if hasattr(k_st, "to_pydatetime") else k_st
                        # 🌟 필수: 같은 날짜의 카카오톡 작업만 중복 비교 대상으로 한정
                        if st_dt.date() != k_st_dt.date():
                            continue

                        k_client = str(k.get("client_name", "")).strip()
                        k_desc = str(k.get("task_description", "")).strip()

                        if cls.is_same_task_match(k_client, k_desc, k_st_dt, parsed_client, parsed_desc, subj, st_dt):
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
                        "date_str": date_str_val,
                        "month_str": month_str_val,
                        "week_label": week_label_val,
                        "week_str": week_str_val,
                        "status": status,
                        "is_outlook": True,
                        "is_leave": False,
                        "is_night_work": False,
                        "is_weekend_work": False
                    }
                    outlook_converted_rows.append(row_dict)

        if outlook_converted_rows:
            out_df_converted = pd.DataFrame(outlook_converted_rows)
            # 🛡️ 동일 작업자 동일 날짜/시간대 휴가 중복 방어 (상세 일정 유지)
            if "is_leave" in out_df_converted.columns and out_df_converted["is_leave"].any():
                l_mask = out_df_converted["is_leave"] == True
                out_leaves = out_df_converted[l_mask].drop_duplicates(subset=["worker_name", "date_str", "start_time"], keep="last")
                out_others = out_df_converted[~l_mask]
                out_df_converted = pd.concat([out_others, out_leaves], ignore_index=True)
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

        # ⏱️ [시간 보정 오버라이드 영구 적용] 관리자가 수정한 작업 인정 공수를 최우선 적용
        if not combined_df.empty and "msg_hash" in combined_df.columns:
            try:
                adj_map = db_manager.get_adjusted_hours_map()
                if adj_map:
                    if "is_time_adjusted" not in combined_df.columns:
                        combined_df["is_time_adjusted"] = False
                    if "original_hours" not in combined_df.columns:
                        combined_df["original_hours"] = combined_df.get("actual_hours", 0.0)

                    for mh, adj_h in adj_map.items():
                        m = combined_df["msg_hash"] == mh
                        if m.any():
                            combined_df.loc[m, "is_time_adjusted"] = True
                            combined_df.loc[m, "actual_hours"] = float(adj_h)
                            combined_df.loc[m, "actual_minutes"] = int(float(adj_h) * 60)
                            combined_df.loc[m, "estimated_hours"] = float(adj_h)
                            combined_df.loc[m, "total_hours"] = float(adj_h)
                            if "display_hours" in combined_df.columns:
                                combined_df.loc[m, "display_hours"] = float(adj_h)
            except Exception as e_adj:
                print(f"[보정 시간 오버라이드 알림]: {e_adj}")

        return combined_df
