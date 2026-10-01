from typing import Dict, List, Any, Optional
import pandas as pd
from ..database.supabase_client import db_manager
from .team_service import TeamService

class CostEstimationService:
    """
    프로젝트 및 현장 지원 예상 비용(청구 금액) 산정 서비스
    1. 직급별 시간당 단가 관리 (사원/대리/과장/차장/수석 등)
    2. 업무 시간 직접 수정 및 영구 보존 오버라이드
    3. 조회 기준(기간, 팀, 팀원, 고객사) 기반 예상 청구 금액 실시간 산정
    4. 팀원별, 고객사별, 직급별 다차원 정산 통계 집계
    """

    @classmethod
    def get_hourly_rates(cls) -> Dict[str, int]:
        """직급별 시간당 지원 금액(단가) 딕셔너리 반환 (원/h)"""
        return db_manager.get_hourly_rates()

    @classmethod
    def save_hourly_rates(cls, rates: Dict[str, int]) -> bool:
        """직급별 시간당 지원 금액 저장 (DB 영구 보존)"""
        return db_manager.save_hourly_rates(rates)

    @classmethod
    def calculate_costs(cls, df: pd.DataFrame, custom_rates: Optional[Dict[str, int]] = None) -> pd.DataFrame:
        """
        작업 데이터프레임에 직급, 단가, 청구 인정 공수, 예상 청구 금액을 부여하여 반환
        """
        rates = custom_rates or cls.get_hourly_rates()
        default_rate = rates.get("기타", 50000)

        df_calc = df.copy()

        # 🛡️ 이미 완료(COMPLETED)된 작업만 예상 비용 산정 및 시간 수정 대상으로 포함 (진행 중 PENDING/SCHEDULED 제외)
        if "status" in df_calc.columns:
            comp_mask = df_calc["status"].astype(str).str.upper().isin(["COMPLETED", "완료"])
            df_calc = df_calc[comp_mask].copy()

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
        # 휴가/연차는 청구 금액 0원 (공수 0.0h)
        is_leave_mask = pd.Series(False, index=df_calc.index)
        if "is_leave" in df_calc.columns:
            is_leave_mask = is_leave_mask | df_calc["is_leave"].fillna(False).astype(bool)
        if "log_type" in df_calc.columns:
            is_leave_mask = is_leave_mask | (df_calc["log_type"] == "휴가")

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
    def get_monthly_billing_trend(cls, df_raw: pd.DataFrame, custom_rates: Optional[Dict[str, int]] = None) -> pd.DataFrame:
        """
        월별 청구 추이 및 전월 대비(MoM) 증감률 분석 데이터 집계
        """
        if df_raw.empty:
            return pd.DataFrame()

        # 전체 완료 작업 기준 비용 산정
        df_calc = cls.calculate_costs(df_raw, custom_rates=custom_rates)
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

