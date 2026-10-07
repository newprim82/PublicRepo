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
        leave_kws = ["연차", "반차", "오전반차", "오후반차", "휴가", "공가", "병가", "외출", "조퇴", "병원진료", "건강검진"]
        if "task_description" in df_calc.columns:
            is_leave_mask = is_leave_mask | df_calc["task_description"].astype(str).apply(lambda s: any(kw in s for kw in leave_kws))
        if "client_name" in df_calc.columns:
            is_leave_mask = is_leave_mask | df_calc["client_name"].astype(str).str.contains("휴가|연차|반차", regex=True)

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
        
        # 🏖️ 휴가/연차/반차 항목은 청구 기준이 아니므로 기존공수 및 인정공수 모두 0.0h 강제
        df_calc.loc[is_leave_mask, "original_hours"] = 0.0
        df_calc.loc[is_leave_mask, "billable_hours"] = 0.0

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
    def _create_mom_chart_image(cls, trend_df: pd.DataFrame) -> Optional[bytes]:
        """
        웹 대시보드 Plotly 그래프와 100% 동일한 모던 고화질(DPI 200) 차트 이미지 생성
        - 기본 청구액(다크 틸) + 할증 가산액(에메랄드 그린) 누적 막대
        - 투입 공수(스카이 블루) 보조 Y축 꺾은선 + 데이터 레이블
        """
        try:
            import io
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.font_manager as fm
            import numpy as np

            # 한글 폰트 안전 감지
            font_names = [f.name for f in fm.fontManager.ttflist]
            chosen_font = "DejaVu Sans"
            for candidate in ["Malgun Gothic", "NanumGothic", "AppleGothic", "Noto Sans CJK KR"]:
                if candidate in font_names:
                    chosen_font = candidate
                    break

            plt.rcParams['font.family'] = chosen_font
            plt.rcParams['axes.unicode_minus'] = False

            sorted_df = trend_df.sort_values(by="year_month", ascending=True).reset_index(drop=True)
            x_labels = sorted_df["year_month"].astype(str).tolist()
            x = np.arange(len(x_labels))
            base_cost = sorted_df["base_cost"].astype(float)
            overtime_premium = sorted_df["overtime_premium"].astype(float)
            total_hours = sorted_df["total_hours"].astype(float)

            fig, ax1 = plt.subplots(figsize=(10.5, 4.0), dpi=200, facecolor='#ffffff')
            ax1.set_facecolor('#ffffff')

            bar_width = 0.52
            ax1.bar(x, base_cost, bar_width, label='기본 청구액 (원)', color='#005073', zorder=2)
            ax1.bar(x, overtime_premium, bar_width, bottom=base_cost, label='야간/주말 할증 가산액 (원)', color='#10b981', zorder=2)

            ax1.set_xlabel('월 (YYYY-MM)', fontsize=9.5, fontweight='bold', color='#334155', labelpad=8)
            ax1.set_ylabel('청구 금액 (원)', fontsize=9.5, fontweight='bold', color='#334155', labelpad=8)
            ax1.set_xticks(x)
            ax1.set_xticklabels(x_labels, fontsize=8.5, color='#475569')

            max_cost = (base_cost + overtime_premium).max() if len(sorted_df) > 0 else 10000000
            ax1.set_ylim(0, max_cost * 1.15)
            def currency_fmt(x_val, _):
                if x_val >= 1e8:
                    return f"{x_val/1e8:.1f}억"
                elif x_val >= 1e6:
                    return f"{int(x_val/1e6)}M"
                elif x_val == 0:
                    return "0"
                return f"{int(x_val):,}"
            ax1.yaxis.set_major_formatter(plt.FuncFormatter(currency_fmt))
            ax1.tick_params(axis='y', colors='#475569', labelsize=8.5)
            ax1.grid(axis='y', linestyle='--', linewidth=0.8, color='#e2e8f0', zorder=1)

            ax1.spines['top'].set_visible(False)
            ax1.spines['right'].set_visible(False)
            ax1.spines['left'].set_color('#cbd5e1')
            ax1.spines['bottom'].set_color('#cbd5e1')

            ax2 = ax1.twinx()
            ax2.set_facecolor('none')
            ax2.plot(x, total_hours, color='#0284c7', linewidth=2.6, marker='o', markersize=6.5,
                     markerfacecolor='#0284c7', markeredgecolor='#ffffff', markeredgewidth=1.2,
                     label='투입 공수 (h)', zorder=4)

            max_hours = total_hours.max() if len(sorted_df) > 0 else 100
            ax2.set_ylim(0, max_hours * 1.25)
            ax2.set_ylabel('투입 공수 (h)', fontsize=9.5, fontweight='bold', color='#0284c7', labelpad=8)
            ax2.tick_params(axis='y', colors='#0284c7', labelsize=8.5)
            ax2.spines['top'].set_visible(False)
            ax2.spines['left'].set_visible(False)
            ax2.spines['right'].set_color('#cbd5e1')
            ax2.spines['bottom'].set_visible(False)

            for i_pt, h_val in enumerate(total_hours):
                ax2.annotate(
                    f"{h_val:.1f}h",
                    xy=(x[i_pt], h_val),
                    xytext=(0, 7),
                    textcoords='offset points',
                    ha='center',
                    va='bottom',
                    fontsize=8.5,
                    fontweight='bold',
                    color='#0284c7',
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='#ffffff', edgecolor='none', alpha=0.85)
                )

            plt.title('월별 청구 금액(막대) & 투입 공수(꺾은선) 추이', fontsize=12, fontweight='bold', color='#005073', pad=18, loc='left')

            lines, labels = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines + lines2, labels + labels2, loc='upper right', bbox_to_anchor=(1.0, 1.15),
                       ncol=3, frameon=True, facecolor='#ffffff', edgecolor='#e2e8f0', fontsize=8.5)

            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor='#ffffff')
            plt.close(fig)
            return buf.getvalue()
        except Exception:
            return None

    @classmethod
    def generate_mom_excel_report(
        cls,
        trend_df: pd.DataFrame,
        team_name: str = "전체 팀"
    ) -> bytes:
        """
        월별 청구 추이 및 MoM 분석 완성형 엑셀 보고서 생성 (.xlsx)
        - 상단 대시보드 타이틀 및 4대 핵심 KPI 요약 카드
        - 화면과 100% 동일한 고해상도(DPI 200) 그래프 이미지 시트 삽입 (흐림/조악함 제로)
        - 시각화 스타일링된 월별 정산 내역 및 MoM 지표 데이터 테이블 (숫자 포맷, 테두리, 하이라이트)
        """
        import io
        import openpyxl
        from openpyxl.drawing.image import Image as OpenpyxlImage
        from openpyxl.chart import BarChart, LineChart, Reference
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from datetime import datetime

        output = io.BytesIO()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "MoM_청구추이분석"
        ws.views.sheetView[0].showGridLines = True

        display_team = team_name if team_name and team_name != "전체 팀" else "전체 기술본부"

        # 테마 색상 팔레트 (Cisco Blue & Modern Tech Theme)
        c_navy = "005073"
        c_blue = "0284C7"
        c_green = "10B981"
        c_purple = "8B5CF6"
        c_gray = "64748B"
        c_border = "CBD5E1"
        c_bg_head = "F1F5F9"

        border_card = Border(
            left=Side(style='thin', color=c_border),
            right=Side(style='thin', color=c_border),
            top=Side(style='thin', color=c_border),
            bottom=Side(style='thin', color=c_border)
        )
        border_grid = Border(
            left=Side(style='thin', color="E2E8F0"),
            right=Side(style='thin', color="E2E8F0"),
            top=Side(style='thin', color="E2E8F0"),
            bottom=Side(style='thin', color="E2E8F0")
        )

        # 1. 상단 타이틀 & 서브타이틀
        ws['A1'] = f"[{display_team}] 월별 청구 추이 및 전월 대비(MoM) 증감 분석 보고서"
        ws['A1'].font = Font(name="맑은 고딕", size=15, bold=True, color=c_navy)
        ws['A1'].alignment = Alignment(vertical="center")
        ws.merge_cells('A1:J1')
        ws.row_dimensions[1].height = 26

        ws['A2'] = f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 기준: LGU+ time.bora.net NTP 타임서버 동기화"
        ws['A2'].font = Font(name="맑은 고딕", size=9, color=c_gray)
        ws['A2'].alignment = Alignment(vertical="center")
        ws.merge_cells('A2:J2')
        ws.row_dimensions[2].height = 16

        # 2. 상단 4대 핵심 KPI 카드
        if not trend_df.empty:
            latest = trend_df.iloc[-1]
            prev = trend_df.iloc[-2] if len(trend_df) >= 2 else None

            c_pct = latest.get("mom_cost_pct", 0.0)
            c_diff = int(latest.get("mom_diff_cost", 0))
            c_sub = "전월 데이터 없음" if prev is None or pd.isna(c_pct) else (f"MoM ▲ +{c_pct:.1f}% (+₩{c_diff:,})" if c_diff >= 0 else f"MoM ▼ {c_pct:.1f}% (-₩{abs(c_diff):,})")

            h_pct = latest.get("mom_hours_pct", 0.0)
            h_diff = float(latest.get("mom_diff_hours", 0.0))
            h_sub = "전월 데이터 없음" if prev is None or pd.isna(h_pct) else (f"MoM ▲ +{h_pct:.1f}% (+{h_diff:.1f}h)" if h_diff >= 0 else f"MoM ▼ {h_pct:.1f}% ({h_diff:.1f}h)")

            def draw_kpi_card(start_col, start_row, end_col, label, val_str, sub_str, val_color):
                c_lbl = ws.cell(row=start_row, column=start_col, value=label)
                c_lbl.font = Font(name="맑은 고딕", size=9, bold=True, color="475569")
                c_lbl.fill = PatternFill(start_color=c_bg_head, end_color=c_bg_head, fill_type="solid")
                c_lbl.alignment = Alignment(horizontal="center", vertical="center")

                c_val = ws.cell(row=start_row+1, column=start_col, value=val_str)
                c_val.font = Font(name="맑은 고딕", size=13.5, bold=True, color=val_color)
                c_val.fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
                c_val.alignment = Alignment(horizontal="center", vertical="center")

                c_sub_cell = ws.cell(row=start_row+2, column=start_col, value=sub_str)
                c_sub_cell.font = Font(name="맑은 고딕", size=8.5, bold=True, color=c_gray)
                c_sub_cell.fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
                c_sub_cell.alignment = Alignment(horizontal="center", vertical="center")

                ws.merge_cells(start_row=start_row, start_column=start_col, end_row=start_row, end_column=end_col)
                ws.merge_cells(start_row=start_row+1, start_column=start_col, end_row=start_row+1, end_column=end_col)
                ws.merge_cells(start_row=start_row+2, start_column=start_col, end_row=start_row+2, end_column=end_col)

                for r in range(start_row, start_row + 3):
                    for c in range(start_col, end_col + 1):
                        ws.cell(row=r, column=c).border = border_card

            draw_kpi_card(1, 4, 2, f"{latest['year_month']} 청구 금액", f"₩ {int(latest['total_cost']):,}", c_sub, c_navy)
            draw_kpi_card(3, 4, 4, f"{latest['year_month']} 투입 인정 공수", f"{latest['total_hours']:.1f} h", h_sub, c_blue)
            draw_kpi_card(5, 4, 7, "기본 vs 할증 가산액", f"+₩ {int(latest['overtime_premium']):,}", f"기본: ₩{int(latest['base_cost']):,} (야간/주말 {latest['overtime_hours']:.1f}h)", c_green)
            draw_kpi_card(8, 4, 10, f"{latest['year_month']} 투입 인원 / 건수", f"{int(latest['worker_count'])}명", f"총 {int(latest['task_count']):,}건 완료 작업", c_purple)

            ws.row_dimensions[4].height = 18
            ws.row_dimensions[5].height = 22
            ws.row_dimensions[6].height = 18

        # 3. 고화질 그래프 이미지 삽입 (A8 위치, 웹 화면 캡처급 퀄리티)
        chart_inserted = False
        chart_bytes = cls._create_mom_chart_image(trend_df)
        if chart_bytes:
            try:
                chart_img = OpenpyxlImage(io.BytesIO(chart_bytes))
                chart_img.width = 840
                chart_img.height = 320
                ws.add_image(chart_img, 'A8')
                chart_inserted = True
            except Exception:
                chart_inserted = False

        # 4. 데이터 테이블 영역 (행 26)
        table_start_row = 26
        headers = [
            "월(YYYY-MM)", "최종 청구금액(원)", "기본금액(원)", "할증가산액(원)", "MoM 금액증감(%)",
            "총 인정공수(h)", "야간·주말(h)", "MoM 공수증감(%)", "투입인원", "작업건수"
        ]
        fill_th = PatternFill(start_color=c_navy, end_color=c_navy, fill_type="solid")
        font_th = Font(name="맑은 고딕", size=9.5, bold=True, color="FFFFFF")
        align_center = Alignment(horizontal="center", vertical="center")

        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=table_start_row, column=col_idx, value=h)
            cell.fill = fill_th
            cell.font = font_th
            cell.alignment = align_center
            cell.border = border_card
        ws.row_dimensions[table_start_row].height = 24

        sorted_df = trend_df.sort_values(by="year_month", ascending=False).reset_index(drop=True)
        num_rows = len(sorted_df)

        for r_idx, (_, row) in enumerate(sorted_df.iterrows()):
            curr_r = table_start_row + 1 + r_idx
            ws.row_dimensions[curr_r].height = 20

            c1 = ws.cell(row=curr_r, column=1, value=str(row['year_month']))
            c1.alignment = align_center

            c2 = ws.cell(row=curr_r, column=2, value=int(row['total_cost']))
            c2.number_format = '₩ #,##0'
            c2.alignment = Alignment(horizontal="right", vertical="center")
            c2.font = Font(name="맑은 고딕", size=9, bold=True, color=c_navy)

            c3 = ws.cell(row=curr_r, column=3, value=int(row['base_cost']))
            c3.number_format = '₩ #,##0'
            c3.alignment = Alignment(horizontal="right", vertical="center")

            c4 = ws.cell(row=curr_r, column=4, value=int(row['overtime_premium']))
            c4.number_format = '+₩ #,##0'
            c4.alignment = Alignment(horizontal="right", vertical="center")
            c4.font = Font(name="맑은 고딕", size=9, color=c_green)

            c_pct = row.get("mom_cost_pct")
            c_diff = row.get("mom_diff_cost", 0)
            c_txt = "-" if pd.isna(c_pct) else (f"+{c_pct:.1f}%" if c_diff >= 0 else f"{c_pct:.1f}%")
            c5 = ws.cell(row=curr_r, column=5, value=c_txt)
            c5.alignment = align_center

            c6 = ws.cell(row=curr_r, column=6, value=float(row['total_hours']))
            c6.number_format = '#,##0.0 "h"'
            c6.alignment = Alignment(horizontal="right", vertical="center")
            c6.font = Font(name="맑은 고딕", size=9, bold=True, color=c_blue)

            c7 = ws.cell(row=curr_r, column=7, value=float(row['overtime_hours']))
            c7.number_format = '#,##0.0 "h"'
            c7.alignment = Alignment(horizontal="right", vertical="center")

            h_pct = row.get("mom_hours_pct")
            h_diff = row.get("mom_diff_hours", 0)
            h_txt = "-" if pd.isna(h_pct) else (f"+{h_pct:.1f}%" if h_diff >= 0 else f"{h_pct:.1f}%")
            c8 = ws.cell(row=curr_r, column=8, value=h_txt)
            c8.alignment = align_center

            c9 = ws.cell(row=curr_r, column=9, value=int(row['worker_count']))
            c9.number_format = '#,##0 "명"'
            c9.alignment = align_center

            c10 = ws.cell(row=curr_r, column=10, value=int(row['task_count']))
            c10.number_format = '#,##0 "건"'
            c10.alignment = align_center

            for col_i in range(1, 11):
                cell = ws.cell(row=curr_r, column=col_i)
                cell.border = border_grid
                if not cell.font or cell.font.name != "맑은 고딕":
                    cell.font = Font(name="맑은 고딕", size=9)

        col_widths = [14, 18, 16, 16, 15, 15, 14, 15, 12, 12]
        for i, w in enumerate(col_widths, 1):
            col_letter = get_column_letter(i)
            ws.column_dimensions[col_letter].width = w

        # 만약 고화질 이미지 삽입이 실패했을 때만 openpyxl 네이티브 차트로 안전 폴백
        if not chart_inserted and num_rows > 0:
            chart1 = BarChart()
            chart1.type = "col"
            chart1.grouping = "stacked"
            chart1.overlap = 100
            chart1.title = "월별 청구 금액(막대) & 투입 공수(꺾은선) 추이"
            chart1.y_axis.title = "청구 금액 (원)"
            chart1.x_axis.title = "월 (YYYY-MM)"
            chart1.width = 24
            chart1.height = 11

            data1 = Reference(ws, min_col=3, min_row=table_start_row, max_col=4, max_row=table_start_row + num_rows)
            cats = Reference(ws, min_col=1, min_row=table_start_row + 1, max_row=table_start_row + num_rows)
            chart1.add_data(data1, titles_from_data=True)
            chart1.set_categories(cats)

            chart2 = LineChart()
            data2 = Reference(ws, min_col=6, min_row=table_start_row, max_row=table_start_row + num_rows)
            chart2.add_data(data2, titles_from_data=True)
            chart2.y_axis.title = "투입 공수 (h)"
            chart2.y_axis.axId = 200
            chart2.y_axis.crosses = "max"

            chart1 += chart2
            ws.add_chart(chart1, "A8")

        wb.save(output)
        return output.getvalue()

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

