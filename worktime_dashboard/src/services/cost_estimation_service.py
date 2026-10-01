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

        # 완료 작업이 0건이거나 빈 데이터프레임일 때 조기 반환 (TypeError 방지)
        if df_calc.empty:
            empty_df = df_calc.copy()
            for col in ["hourly_rate", "billable_hours", "estimated_cost", "is_time_adjusted"]:
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

        # 예상 청구 금액 = 청구 인정 공수 * 직급별 단가 (안전한 수치형 연산)
        calc_cost = (df_calc["billable_hours"].astype(float) * df_calc["hourly_rate"].astype(float)).round()
        df_calc["estimated_cost"] = pd.to_numeric(calc_cost, errors="coerce").fillna(0).astype(int)

        # 보정 여부 플래그
        if "is_time_adjusted" not in df_calc.columns:
            df_calc["is_time_adjusted"] = False

        return df_calc

    @classmethod
    def get_cost_summary_kpis(cls, df_calc: pd.DataFrame) -> Dict[str, Any]:
        """
        예상 비용 산정 상단 4대 KPI 메트릭 요약 반환
        """
        if df_calc.empty:
            return {
                "total_cost": 0,
                "total_billable_hours": 0.0,
                "worker_count": 0,
                "avg_hourly_rate": 0,
                "adjusted_count": 0,
                "total_tasks": 0
            }

        total_cost = int(df_calc["estimated_cost"].sum())
        total_billable_hours = round(float(df_calc["billable_hours"].sum()), 1)
        worker_count = int(df_calc["worker_name"].nunique()) if "worker_name" in df_calc.columns else 0
        
        # 가중 평균 시간당 단가 (총 금액 / 총 시간)
        avg_hourly_rate = int(round(total_cost / total_billable_hours)) if total_billable_hours > 0 else 0

        # 보정된 작업 수
        adj_count = int(df_calc["is_time_adjusted"].sum()) if "is_time_adjusted" in df_calc.columns else 0
        total_tasks = len(df_calc)

        return {
            "total_cost": total_cost,
            "total_billable_hours": total_billable_hours,
            "worker_count": worker_count,
            "avg_hourly_rate": avg_hourly_rate,
            "adjusted_count": adj_count,
            "total_tasks": total_tasks
        }

    @classmethod
    def get_worker_cost_summary(cls, df_calc: pd.DataFrame) -> pd.DataFrame:
        """
        팀원별 예상 청구 금액 및 투입 공수 정산표 집계
        """
        if df_calc.empty or "worker_name" not in df_calc.columns:
            return pd.DataFrame()

        grouped = df_calc.groupby("worker_name").agg(
            worker_team=("worker_team", "first"),
            worker_title=("worker_title", "first"),
            hourly_rate=("hourly_rate", "first"),
            total_hours=("billable_hours", "sum"),
            total_cost=("estimated_cost", "sum"),
            task_count=("task_description", "count") if "task_description" in df_calc.columns else ("worker_name", "count"),
            adjusted_count=("is_time_adjusted", "sum") if "is_time_adjusted" in df_calc.columns else ("worker_name", lambda x: 0)
        ).reset_index()

        grouped["total_hours"] = grouped["total_hours"].round(1)
        grouped["total_cost"] = grouped["total_cost"].astype(int)
        grouped["adjusted_count"] = grouped["adjusted_count"].astype(int)

        # 금액 내림차순 정렬
        grouped = grouped.sort_values(by="total_cost", ascending=False).reset_index(drop=True)
        return grouped

    @classmethod
    def get_client_cost_summary(cls, df_calc: pd.DataFrame) -> pd.DataFrame:
        """
        고객사별 예상 청구 금액 및 투입 공수 정산표 집계
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
            total_cost=("estimated_cost", "sum"),
            task_count=("task_description", "count") if "task_description" in non_leave_df.columns else ("client_name", "count"),
            adjusted_count=("is_time_adjusted", "sum") if "is_time_adjusted" in non_leave_df.columns else ("client_name", lambda x: 0)
        ).reset_index()

        grouped["total_hours"] = grouped["total_hours"].round(1)
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
            total_cost=("estimated_cost", "sum"),
            task_count=("billable_hours", "count")
        ).reset_index()

        grouped["total_hours"] = grouped["total_hours"].round(1)
        grouped["total_cost"] = grouped["total_cost"].astype(int)

        total_cost_sum = grouped["total_cost"].sum()
        if total_cost_sum > 0:
            grouped["cost_share_pct"] = (grouped["total_cost"] / total_cost_sum * 100).round(1)
        else:
            grouped["cost_share_pct"] = 0.0

        # 직급 순서 정렬 (수석 -> 차장 -> 과장 -> 대리 -> 사원)
        order_dict = {"수석": 1, "차장": 2, "과장": 3, "대리": 4, "사원": 5, "기타": 6}
        grouped["sort_order"] = grouped["worker_title"].map(lambda x: order_dict.get(x, 99))
        grouped = grouped.sort_values(by="sort_order").drop(columns=["sort_order"]).reset_index(drop=True)

        return grouped

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
