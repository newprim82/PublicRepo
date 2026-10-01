import os
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
from ..config import config
from ..database.supabase_client import db_manager
from .team_service import TeamService

class CostEstimationService:
    """
    프로젝트 및 현장 지원 예상 비용(청구 금액) 산정 서비스
    1. 직급별 시간당 단가 관리 (사원/대리/과장/차장/수석 등)
    2. 업무 시간 직접 수정 및 영구 보존 오버라이드
    3. 조회 기준(기간, 팀, 팀원, 고객사) 기반 예상 청구 금액 실시간 산정
    4. 팀원별, 고객사별, 직급별 다차원 정산 통계 집계
    5. 비청구 고객사/사내업무(1on1, 내부업무 등) 영구 제외 관리
    """

    EXCLUDED_CLIENTS_FILE = config.LOCAL_DB_PATH.parent / "excluded_cost_clients.json"
    DEFAULT_EXCLUDED_CLIENTS = ["1on1", "내부업무"]
    _cached_excluded_clients: Optional[List[str]] = None

    @classmethod
    def get_excluded_clients(cls) -> List[str]:
        """
        청구 금액 정산에서 제외할 고객사/사내업무 목록 조회
        기본값: ["1on1", "내부업무"]
        """
        if cls._cached_excluded_clients is not None:
            return list(cls._cached_excluded_clients)

        excluded: List[str] = []

        # 1. Supabase 조회 시도
        try:
            if db_manager.use_supabase and db_manager.supabase:
                res = db_manager.supabase.table("worktime_excluded_cost_clients").select("client_name").execute()
                if res.data:
                    for r in res.data:
                        c = str(r.get("client_name", "")).strip()
                        if c and c not in excluded:
                            excluded.append(c)
        except Exception:
            pass

        # 2. 로컬 SQLite 조회 시도
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS excluded_cost_clients (
                    client_name TEXT PRIMARY KEY,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)
            cursor.execute("SELECT client_name FROM excluded_cost_clients")
            for (c,) in cursor.fetchall():
                c_str = str(c).strip()
                if c_str and c_str not in excluded:
                    excluded.append(c_str)
            conn.close()
        except Exception:
            pass

        # 3. 로컬 JSON 파일 조회
        if cls.EXCLUDED_CLIENTS_FILE.exists():
            try:
                with open(cls.EXCLUDED_CLIENTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for c in data:
                            c_str = str(c).strip()
                            if c_str and c_str not in excluded:
                                excluded.append(c_str)
            except Exception:
                pass

        # 기본값 병합 (비어있으면 기본값 적용 및 자동 영구 저장)
        if not excluded:
            excluded = list(cls.DEFAULT_EXCLUDED_CLIENTS)
            try:
                cls.save_excluded_clients(excluded)
            except Exception:
                pass

        cls._cached_excluded_clients = excluded
        return list(excluded)

    @classmethod
    def save_excluded_clients(cls, clients: List[str]) -> bool:
        """
        청구 금액 정산에서 제외할 고객사/사내업무 목록 영구 저장
        (로컬 JSON, 로컬 SQLite, Supabase 동시 저장)
        """
        clean_clients = []
        seen = set()
        for c in clients:
            c_str = str(c).strip()
            if c_str and c_str.lower() not in seen:
                seen.add(c_str.lower())
                clean_clients.append(c_str)

        cls._cached_excluded_clients = clean_clients

        # 1. 로컬 JSON 저장
        try:
            cls.EXCLUDED_CLIENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(cls.EXCLUDED_CLIENTS_FILE, "w", encoding="utf-8") as f:
                json.dump(clean_clients, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[CostEstimationService] JSON 저장 오류: {e}")

        # 2. 로컬 SQLite 저장
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS excluded_cost_clients (
                    client_name TEXT PRIMARY KEY,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)
            cursor.execute("DELETE FROM excluded_cost_clients")
            cursor.executemany(
                "INSERT INTO excluded_cost_clients (client_name) VALUES (?)",
                [(c,) for c in clean_clients]
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[CostEstimationService] SQLite 저장 오류: {e}")

        # 3. Supabase 저장 시도
        try:
            if db_manager.use_supabase and db_manager.supabase:
                payloads = [{"client_name": c} for c in clean_clients]
                if payloads:
                    db_manager.supabase.table("worktime_excluded_cost_clients").upsert(payloads).execute()
        except Exception:
            pass

        return True

    @classmethod
    def get_hourly_rates(cls) -> Dict[str, int]:
        """직급별 시간당 지원 금액(단가) 딕셔너리 반환 (원/h)"""
        return db_manager.get_hourly_rates()

    @classmethod
    def save_hourly_rates(cls, rates: Dict[str, int]) -> bool:
        """직급별 시간당 지원 금액 저장 (DB 영구 보존)"""
        return db_manager.save_hourly_rates(rates)

    @classmethod
    def calculate_costs(
        cls,
        df: pd.DataFrame,
        custom_rates: Optional[Dict[str, int]] = None,
        excluded_clients: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        작업 데이터프레임에 직급, 단가, 청구 인정 공수, 예상 청구 금액을 부여하여 반환
        """
        rates = custom_rates or cls.get_hourly_rates()
        default_rate = rates.get("기타", 50000)

        df_calc = df.copy()

        # 🛡️ 1. 이미 완료(COMPLETED)된 작업만 예상 비용 산정 및 시간 수정 대상으로 포함 (진행 중 PENDING/SCHEDULED 제외)
        if "status" in df_calc.columns:
            comp_mask = df_calc["status"].astype(str).str.upper().isin(["COMPLETED", "완료"])
            df_calc = df_calc[comp_mask].copy()

        # 🎓 2. 구분(log_type) 자체가 '교육'인 항목은 비용 산정 대상에서 원천 제외 (사내/수강 교육으로 고객사 비용 청구 불가)
        if "log_type" in df_calc.columns:
            edu_mask = df_calc["log_type"].astype(str).str.strip() == "교육"
            df_calc = df_calc[~edu_mask].copy()

        # 🚫 3. 비청구 대상(1on1, 사내업무 등) 고객사 원천 제외 필터링
        if excluded_clients is None:
            excluded_clients = cls.get_excluded_clients()

        if excluded_clients and "client_name" in df_calc.columns:
            ex_set = {str(c).strip().lower() for c in excluded_clients if str(c).strip()}
            if ex_set:
                client_clean_series = df_calc["client_name"].astype(str).str.strip().str.lower()
                df_calc = df_calc[~client_clean_series.isin(ex_set)].copy()

        #完了 작업이 0건이거나 빈 데이터프레임일 때 조기 반환 (TypeError 방지)
        if df_calc.empty:
            empty_df = df_calc.copy()
            for col in [
                "hourly_rate", "billable_hours", "base_cost", "estimated_cost",
                "overtime_premium", "overtime_hours", "is_time_adjusted", "is_overtime", "rate_multiplier"
            ]:
                if col not in empty_df.columns:
                    empty_df[col] = 0
            return empty_df

        title_map = TeamService.get_title_mappings()
        team_map = TeamService.get_team_mappings()

        # 직급 동기화
        if "worker_name" in df_calc.columns:
            if "worker_title" not in df_calc.columns or df_calc["worker_title"].isna().all():
                df_calc["worker_title"] = df_calc["worker_name"].map(title_map).fillna("기타")
            else:
                df_calc["worker_title"] = df_calc["worker_title"].fillna(df_calc["worker_name"].map(title_map)).fillna("기타")
            
            if "worker_team" not in df_calc.columns or df_calc["worker_team"].isna().all():
                df_calc["worker_team"] = df_calc["worker_name"].map(team_map).fillna("미배정")

        # 직급별 단가 매핑
        def _get_rate(title):
            t_str = str(title).strip()
            # 정확한 매칭 우선
            if t_str in rates:
                return rates[t_str]
            # 부분 문자열 매칭 (예: '수석엔지니어' -> '수석')
            for k, v in rates.items():
                if k in t_str:
                    return v
            return default_rate

        df_calc["hourly_rate"] = pd.to_numeric(
            df_calc["worker_title"].apply(_get_rate), errors="coerce"
        ).fillna(default_rate).astype(int)

        # 청구 인정 공수(billable_hours) 산정
        # 휴가/연차 및 교육은 청구 금액 0원 (공수 0.0h)
        is_leave_mask = pd.Series(False, index=df_calc.index)
        if "is_leave" in df_calc.columns:
            is_leave_mask = is_leave_mask | df_calc["is_leave"].fillna(False).astype(bool)
        if "log_type" in df_calc.columns:
            is_leave_mask = is_leave_mask | (df_calc["log_type"].astype(str).str.strip().isin(["휴가", "교육"]))

        # 기본 공수 확보
        if "actual_hours" in df_calc.columns:
            raw_hours = pd.to_numeric(df_calc["actual_hours"], errors="coerce").fillna(0.0)
        elif "estimated_hours" in df_calc.columns:
            raw_hours = pd.to_numeric(df_calc["estimated_hours"], errors="coerce").fillna(0.0)
        elif "total_hours" in df_calc.columns:
            raw_hours = pd.to_numeric(df_calc["total_hours"], errors="coerce").fillna(0.0)
        else:
            raw_hours = pd.Series(0.0, index=df_calc.index)

        # 음수 공수 방어
        raw_hours = pd.to_numeric(raw_hours, errors="coerce").fillna(0.0).clip(lower=0.0)

        # 휴가는 0.0h 강제, 일반 업무는 raw_hours
        df_calc["billable_hours"] = raw_hours
        df_calc.loc[is_leave_mask, "billable_hours"] = 0.0

        # ⏱️ 수파베이스/로컬 보정 공수 맵 매핑 (사용자가 직접 수정한 인정 공수 영구 반영)
        df_calc["is_time_adjusted"] = False
        if "original_hours" not in df_calc.columns:
            df_calc["original_hours"] = df_calc["billable_hours"]
        if "note" not in df_calc.columns:
            df_calc["note"] = ""

        adj_records = db_manager.get_adjusted_records_map()
        if adj_records and "msg_hash" in df_calc.columns:
            for idx, mh in df_calc["msg_hash"].items():
                mh_str = str(mh).strip()
                if mh_str in adj_records:
                    rec = adj_records[mh_str]
                    orig_val = float(rec.get("original_hours", df_calc.at[idx, "billable_hours"]))
                    adj_val = float(rec.get("adjusted_hours", df_calc.at[idx, "billable_hours"]))
                    df_calc.at[idx, "original_hours"] = orig_val
                    df_calc.at[idx, "billable_hours"] = adj_val
                    df_calc.at[idx, "is_time_adjusted"] = True
                    df_calc.at[idx, "note"] = str(rec.get("note", ""))

        # ⚖️ 근로기준법 제56조 준수: 야간(22:00~06:00) 및 주말·휴일 지원 1.5배 가산 상시 자동 적용
        is_night = pd.Series(False, index=df_calc.index)
        is_weekend = pd.Series(False, index=df_calc.index)
        if "is_night_work" in df_calc.columns:
            is_night = df_calc["is_night_work"].fillna(False).astype(bool)
        if "is_weekend_work" in df_calc.columns:
            is_weekend = df_calc["is_weekend_work"].fillna(False).astype(bool)

        df_calc["is_overtime"] = is_night | is_weekend
        df_calc["rate_multiplier"] = df_calc["is_overtime"].apply(lambda x: 1.5 if x else 1.0)
        df_calc["overtime_hours"] = df_calc["billable_hours"].where(df_calc["is_overtime"], 0.0).round(1)

        # 기본 금액 (할증 전 기본 단가 기준)
        base_cost_series = (df_calc["billable_hours"].astype(float) * df_calc["hourly_rate"].astype(float)).round()
        df_calc["base_cost"] = pd.to_numeric(base_cost_series, errors="coerce").fillna(0).astype(int)

        # 최종 예상 청구 금액 = 기본 금액 * 할증배율(1.5 또는 1.0)
        final_cost_series = (df_calc["billable_hours"].astype(float) * df_calc["hourly_rate"].astype(float) * df_calc["rate_multiplier"].astype(float)).round()
        df_calc["estimated_cost"] = pd.to_numeric(final_cost_series, errors="coerce").fillna(0).astype(int)

        # 야간/주말 할증 가산액 (0.5배분)
        df_calc["overtime_premium"] = df_calc["estimated_cost"] - df_calc["base_cost"]

        return df_calc

    @classmethod
    def get_cost_summary_kpis(cls, df_calc: pd.DataFrame) -> Dict[str, Any]:
        """
        예상 비용 산정 상단 4대 KPI 메트릭 요약 반환 (근로기준법 1.5배 할증 메트릭 포함)
        """
        if df_calc.empty:
            return {
                "total_cost": 0,
                "total_base_cost": 0,
                "total_overtime_premium": 0,
                "total_billable_hours": 0.0,
                "total_overtime_hours": 0.0,
                "worker_count": 0,
                "avg_hourly_rate": 0,
                "adjusted_count": 0,
                "total_tasks": 0
            }

        total_cost = int(df_calc["estimated_cost"].sum())
        total_base_cost = int(df_calc["base_cost"].sum()) if "base_cost" in df_calc.columns else total_cost
        total_overtime_premium = int(df_calc["overtime_premium"].sum()) if "overtime_premium" in df_calc.columns else 0
        total_billable_hours = round(float(df_calc["billable_hours"].sum()), 1)
        total_overtime_hours = round(float(df_calc["overtime_hours"].sum()), 1) if "overtime_hours" in df_calc.columns else 0.0
        worker_count = int(df_calc["worker_name"].nunique()) if "worker_name" in df_calc.columns else 0
        
        # 가중 평균 시간당 단가 (총 금액 / 총 시간)
        avg_hourly_rate = int(round(total_cost / total_billable_hours)) if total_billable_hours > 0 else 0

        # 보정된 작업 수
        adj_count = int(df_calc["is_time_adjusted"].sum()) if "is_time_adjusted" in df_calc.columns else 0
        total_tasks = len(df_calc)

        return {
            "total_cost": total_cost,
            "total_base_cost": total_base_cost,
            "total_overtime_premium": total_overtime_premium,
            "total_billable_hours": total_billable_hours,
            "total_overtime_hours": total_overtime_hours,
            "worker_count": worker_count,
            "avg_hourly_rate": avg_hourly_rate,
            "adjusted_count": adj_count,
            "total_tasks": total_tasks
        }

    @classmethod
    def get_worker_cost_summary(cls, df_calc: pd.DataFrame) -> pd.DataFrame:
        """
        팀원별 예상 청구 금액 및 투입 공수 정산표 집계 (야간/주말 할증 가산액 분리 집계)
        """
        if df_calc.empty or "worker_name" not in df_calc.columns:
            return pd.DataFrame()

        grouped = df_calc.groupby("worker_name").agg(
            worker_team=("worker_team", "first"),
            worker_title=("worker_title", "first"),
            hourly_rate=("hourly_rate", "first"),
            total_hours=("billable_hours", "sum"),
            overtime_hours=("overtime_hours", "sum") if "overtime_hours" in df_calc.columns else ("billable_hours", lambda x: 0.0),
            base_cost=("base_cost", "sum") if "base_cost" in df_calc.columns else ("estimated_cost", "sum"),
            overtime_premium=("overtime_premium", "sum") if "overtime_premium" in df_calc.columns else ("estimated_cost", lambda x: 0),
            total_cost=("estimated_cost", "sum"),
            task_count=("task_description", "count") if "task_description" in df_calc.columns else ("worker_name", "count"),
            adjusted_count=("is_time_adjusted", "sum") if "is_time_adjusted" in df_calc.columns else ("worker_name", lambda x: 0)
        ).reset_index()

        grouped["total_hours"] = grouped["total_hours"].round(1)
        grouped["overtime_hours"] = grouped["overtime_hours"].round(1)
        grouped["base_cost"] = grouped["base_cost"].astype(int)
        grouped["overtime_premium"] = grouped["overtime_premium"].astype(int)
        grouped["total_cost"] = grouped["total_cost"].astype(int)
        grouped["adjusted_count"] = grouped["adjusted_count"].astype(int)

        # 금액 내림차순 정렬
        grouped = grouped.sort_values(by="total_cost", ascending=False).reset_index(drop=True)
        return grouped

    @classmethod
    def get_client_cost_summary(cls, df_calc: pd.DataFrame) -> pd.DataFrame:
        """
        고객사별 예상 청구 금액 및 투입 공수 정산표 집계 (야간/주말 할증 가산액 분리 집계)
        """
        if df_calc.empty or "client_name" not in df_calc.columns:
            return pd.DataFrame()

        # 휴가 행은 고객사 정산에서 제외
        non_leave_df = df_calc[~df_calc.get("is_leave", pd.Series(False, index=df_calc.index)).fillna(False).astype(bool)]
        if non_leave_df.empty:
            return pd.DataFrame()

        grouped = non_leave_df.groupby("client_name").agg(
            worker_count=("worker_name", "nunique"),
            total_hours=("billable_hours", "sum"),
            overtime_hours=("overtime_hours", "sum") if "overtime_hours" in non_leave_df.columns else ("billable_hours", lambda x: 0.0),
            base_cost=("base_cost", "sum") if "base_cost" in non_leave_df.columns else ("estimated_cost", "sum"),
            overtime_premium=("overtime_premium", "sum") if "overtime_premium" in non_leave_df.columns else ("estimated_cost", lambda x: 0),
            total_cost=("estimated_cost", "sum"),
            task_count=("task_description", "count") if "task_description" in non_leave_df.columns else ("client_name", "count"),
            adjusted_count=("is_time_adjusted", "sum") if "is_time_adjusted" in non_leave_df.columns else ("client_name", lambda x: 0)
        ).reset_index()

        grouped["total_hours"] = grouped["total_hours"].round(1)
        grouped["overtime_hours"] = grouped["overtime_hours"].round(1)
        grouped["base_cost"] = grouped["base_cost"].astype(int)
        grouped["overtime_premium"] = grouped["overtime_premium"].astype(int)
        grouped["total_cost"] = grouped["total_cost"].astype(int)
        grouped["adjusted_count"] = grouped["adjusted_count"].astype(int)

        # 금액 내림차순 정렬
        grouped = grouped.sort_values(by="total_cost", ascending=False).reset_index(drop=True)
        return grouped

    @classmethod
    def get_title_cost_summary(cls, df_calc: pd.DataFrame) -> pd.DataFrame:
        """
        직급별 청구 금액 및 투입 공수 비중 집계
        """
        if df_calc.empty or "worker_title" not in df_calc.columns:
            return pd.DataFrame()

        grouped = df_calc.groupby("worker_title").agg(
            hourly_rate=("hourly_rate", "first"),
            worker_count=("worker_name", "nunique"),
            total_hours=("billable_hours", "sum"),
            overtime_hours=("overtime_hours", "sum") if "overtime_hours" in df_calc.columns else ("billable_hours", lambda x: 0.0),
            base_cost=("base_cost", "sum") if "base_cost" in df_calc.columns else ("estimated_cost", "sum"),
            overtime_premium=("overtime_premium", "sum") if "overtime_premium" in df_calc.columns else ("estimated_cost", lambda x: 0),
            total_cost=("estimated_cost", "sum"),
            task_count=("billable_hours", "count")
        ).reset_index()

        grouped["total_hours"] = grouped["total_hours"].round(1)
        grouped["overtime_hours"] = grouped["overtime_hours"].round(1)
        grouped["base_cost"] = grouped["base_cost"].astype(int)
        grouped["overtime_premium"] = grouped["overtime_premium"].astype(int)
        grouped["total_cost"] = grouped["total_cost"].astype(int)

        total_cost_sum = grouped["total_cost"].sum()
        if total_cost_sum > 0:
            grouped["cost_share_pct"] = (grouped["total_cost"] / total_cost_sum * 100).round(1)
        else:
            grouped["cost_share_pct"] = 0.0

        # 직급 순서 정렬 (수석 -> 과장 -> 대리 -> 사원)
        order_dict = {"수석": 1, "과장": 2, "대리": 3, "사원": 4}
        grouped["sort_order"] = grouped["worker_title"].map(lambda x: order_dict.get(x, 99))
        grouped = grouped.sort_values(by="sort_order").drop(columns=["sort_order"]).reset_index(drop=True)

        return grouped

    @classmethod
    def get_monthly_billing_trend(
        cls,
        df_raw: pd.DataFrame,
        custom_rates: Optional[Dict[str, int]] = None,
        excluded_clients: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        월별 청구 추이 및 전월 대비(MoM) 증감률 분석 데이터 집계
        """
        if df_raw.empty:
            return pd.DataFrame()

        # 전체 완료 작업 기준 비용 산정 (제외 대상 고객사 반영)
        df_calc = cls.calculate_costs(df_raw, custom_rates=custom_rates, excluded_clients=excluded_clients)
        if df_calc.empty:
            return pd.DataFrame()

        # 월(YYYY-MM) 컬럼 추출
        if "month_str" in df_calc.columns and df_calc["month_str"].notna().any():
            df_calc["year_month"] = df_calc["month_str"].astype(str)
        elif "work_date" in df_calc.columns and df_calc["work_date"].notna().any():
            df_calc["year_month"] = pd.to_datetime(df_calc["work_date"], errors="coerce").dt.strftime("%Y-%m")
        elif "start_time" in df_calc.columns and df_calc["start_time"].notna().any():
            df_calc["year_month"] = pd.to_datetime(df_calc["start_time"], errors="coerce").dt.strftime("%Y-%m")
        else:
            return pd.DataFrame()

        df_calc = df_calc[df_calc["year_month"].notna() & (df_calc["year_month"] != "NaT") & (df_calc["year_month"] != "-")]
        if df_calc.empty:
            return pd.DataFrame()

        monthly = df_calc.groupby("year_month").agg(
            total_cost=("estimated_cost", "sum"),
            base_cost=("base_cost", "sum") if "base_cost" in df_calc.columns else ("estimated_cost", "sum"),
            overtime_premium=("overtime_premium", "sum") if "overtime_premium" in df_calc.columns else ("estimated_cost", lambda x: 0),
            total_hours=("billable_hours", "sum"),
            overtime_hours=("overtime_hours", "sum") if "overtime_hours" in df_calc.columns else ("billable_hours", lambda x: 0.0),
            worker_count=("worker_name", "nunique") if "worker_name" in df_calc.columns else ("billable_hours", lambda x: 1),
            task_count=("billable_hours", "count")
        ).reset_index()

        monthly = monthly.sort_values(by="year_month", ascending=True).reset_index(drop=True)
        monthly["total_cost"] = monthly["total_cost"].astype(int)
        monthly["base_cost"] = monthly["base_cost"].astype(int)
        monthly["overtime_premium"] = monthly["overtime_premium"].astype(int)
        monthly["total_hours"] = monthly["total_hours"].round(1)
        monthly["overtime_hours"] = monthly["overtime_hours"].round(1)

        # 전월 대비 (MoM) 증감액 및 증감률
        monthly["prev_cost"] = monthly["total_cost"].shift(1)
        monthly["mom_diff_cost"] = (monthly["total_cost"] - monthly["prev_cost"]).fillna(0).astype(int)
        monthly["mom_cost_pct"] = ((monthly["total_cost"] - monthly["prev_cost"]) / monthly["prev_cost"].replace(0, float("nan")) * 100).round(1)

        monthly["prev_hours"] = monthly["total_hours"].shift(1)
        monthly["mom_diff_hours"] = (monthly["total_hours"] - monthly["prev_hours"]).fillna(0.0).round(1)
        monthly["mom_hours_pct"] = ((monthly["total_hours"] - monthly["prev_hours"]) / monthly["prev_hours"].replace(0, float("nan")) * 100).round(1)

        return monthly

    @classmethod
    def update_work_log_hours(
        cls,
        msg_hash: str,
        new_hours: float,
        original_hours: float = 0.0,
        note: str = ""
    ) -> bool:
        """
        단건 작업 시간 직접 수정 및 DB 영구 저장
        """
        return db_manager.save_adjusted_work_log(msg_hash, new_hours, original_hours, note)

    @classmethod
    def batch_update_work_log_hours(cls, records: List[Dict[str, Any]]) -> int:
        """
        다건 작업 시간 일괄 수정 및 DB 영구 저장
        """
        return db_manager.batch_save_adjusted_work_logs(records)

    @classmethod
    def save_adjust_history(cls, records: List[Dict[str, Any]]) -> int:
        """
        시간 수정 감사 이력 DB 영구 저장 (누가, 언제, 어떤 작업의 시간을 얼마에서 얼마로 수정했는지)
        """
        return db_manager.save_adjust_history(records)

    @classmethod
    def get_adjust_history(cls, limit: int = 500) -> pd.DataFrame:
        """
        시간 수정 감사 이력 조회 (최신순)
        """
        return db_manager.fetch_adjust_history(limit=limit)

