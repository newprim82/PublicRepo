import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Any, Optional

from src.database.supabase_client import db_manager
try:
    from src.database.supabase_client import fetch_outlook_schedules
except ImportError:
    fetch_outlook_schedules = None
from src.services.team_service import TeamService
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
            return kakao_pend_df, pd.DataFrame(), []

        # 오늘 아웃룩 일정 필터링
        today_out = outlook_df.copy()
        if not pd.api.types.is_datetime64_any_dtype(today_out["start_time"]):
            today_out["start_time"] = pd.to_datetime(today_out["start_time"], errors="coerce")
        if not pd.api.types.is_datetime64_any_dtype(today_out["end_time"]):
            today_out["end_time"] = pd.to_datetime(today_out["end_time"], errors="coerce")

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
            dur_hours = float(r.get("duration_hours") or 9.0)
            w_title = team_info.get(w_name, {}).get("title", "")
            w_team = r.get("worker_team") or team_info.get(w_name, {}).get("team", "미배정")
            l_type = r.get("leave_type") or "연차"

            # 1-A. 오늘 휴가는 상시 실시간 진행 섹션 상단 부재 현황에 100% 카드로 표출
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

            # 1-B. 휴가는 오늘 완료된 작업 섹션에 항상 100% 완료 카드로 당당히 표출!
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
                "estimated_minutes": int(dur_hours * 60),
                "actual_minutes": int(dur_hours * 60),
                "actual_hours": dur_hours,
                "total_hours": dur_hours,
                "status": "COMPLETED",
                "is_outlook": True,
                "is_leave": True,
                "is_night_work": False,
                "is_weekend_work": False
            })

        # 2. 오늘 이미 카카오톡으로 시작보고를 올렸거나 완료한 작업자 확인 (중복 방지)
        kakao_reported_workers = set()
        if not kakao_pend_df.empty and "worker_name" in kakao_pend_df.columns:
            kakao_reported_workers.update(kakao_pend_df["worker_name"].dropna().unique())
        if not today_completed_df.empty and "worker_name" in today_completed_df.columns:
            kakao_reported_workers.update(today_completed_df["worker_name"].dropna().unique())

        # 3. 비-휴가 일반 작업 일정 처리
        work_rows = today_out[today_out["is_leave"] == False]

        for _, r in work_rows.iterrows():
            w_name = r["worker_name"]
            # 카카오톡으로 이미 보고한 작업자는 카톡 보고를 최우선 존중
            if w_name in kakao_reported_workers:
                continue

            st_time = r["start_time"]
            ed_time = r["end_time"]
            if pd.isna(st_time) or pd.isna(ed_time):
                continue

            st_dt = st_time.to_pydatetime() if hasattr(st_time, "to_pydatetime") else st_time
            ed_dt = ed_time.to_pydatetime() if hasattr(ed_time, "to_pydatetime") else ed_time

            total_sec = max(1, (ed_dt - st_dt).total_seconds())
            elapsed_sec = (now - st_dt).total_seconds()
            dur_hours = float(r.get("duration_hours") or round(total_sec / 3600.0, 1))

            w_title = team_info.get(w_name, {}).get("title", "")
            w_team = r.get("worker_team") or team_info.get(w_name, {}).get("team", "미배정")

            # A. 현재 시간이 종료 시각 이후 -> 100% 도달 -> 자동 완료 전환
            if now >= ed_dt:
                auto_completed_rows.append({
                    "msg_hash": f"OUTLOOK_COMP_{r.get('entry_id', '')}",
                    "log_type": "작업",
                    "worker_name": w_name,
                    "worker_title": w_title,
                    "worker_team": w_team,
                    "client_name": r.get("location") or "아웃룩 일정",
                    "task_description": f"[📅 일정완료] {r['subject']}",
                    "start_time": st_time,
                    "end_time": ed_time,
                    "estimated_minutes": int(dur_hours * 60),
                    "actual_minutes": int(dur_hours * 60),
                    "actual_hours": dur_hours,
                    "total_hours": dur_hours,
                    "status": "COMPLETED",
                    "is_outlook": True,
                    "is_night_work": False,
                    "is_weekend_work": False
                })
            # B. 현재 시간이 시작 시각 이후이고 종료 이전 -> 실시간 진행 중 작업 승격
            elif now >= st_dt:
                pct = min(99, max(5, int((elapsed_sec / total_sec) * 100)))
                promoted_pend_rows.append({
                    "msg_hash": f"OUTLOOK_PEND_{r.get('entry_id', '')}",
                    "log_type": "작업",
                    "worker_name": w_name,
                    "worker_title": w_title,
                    "worker_team": w_team,
                    "client_name": r.get("location") or "아웃룩 일정",
                    "task_description": f"[📅 아웃룩] {r['subject']}",
                    "start_time": st_time,
                    "end_time": ed_time,
                    "estimated_minutes": int(dur_hours * 60),
                    "actual_minutes": int((elapsed_sec / 60)),
                    "total_hours": dur_hours,
                    "status": "PENDING",
                    "is_outlook": True,
                    "outlook_progress_pct": pct,
                    "is_night_work": False,
                    "is_weekend_work": False
                })

        # 병합된 진행 중 데이터프레임
        final_pend_df = kakao_pend_df.copy()
        if promoted_pend_rows:
            prom_df = pd.DataFrame(promoted_pend_rows)
            final_pend_df = pd.concat([final_pend_df, prom_df], ignore_index=True)

        auto_comp_df = pd.DataFrame(auto_completed_rows) if auto_completed_rows else pd.DataFrame()

        return final_pend_df, auto_comp_df, leave_records
