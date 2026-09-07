import pandas as pd
import numpy as np
from typing import Dict, Any

class StatsService:
    @staticmethod
    def compute_kpis(df: pd.DataFrame) -> Dict[str, Any]:
        """
        대시보드 상단 주요 KPI 카드 지표 계산
        """
        if df.empty:
            return {
                "total_hours": 0.0,
                "total_tasks": 0,
                "completed_tasks": 0,
                "pending_tasks": 0,
                "active_workers": 0,
                "avg_hours_per_worker": 0.0,
                "night_tasks_count": 0,
                "weekend_tasks_count": 0,
                "overdue_tasks_count": 0,
                "overdue_rate": 0.0,
            }

        # 🌟 미래 예정(SCHEDULED)은 현재 시점 KPI 집계에서 제외하고, 실적(COMPLETED) 및 진행(PENDING)만 집계
        active_df = df[df["status"].isin(["COMPLETED", "PENDING"])] if "status" in df.columns else df

        total_hours = active_df["actual_hours"].sum() if not active_df.empty else 0.0
        total_tasks = len(active_df)
        completed_df = active_df[active_df["status"] == "COMPLETED"] if not active_df.empty else pd.DataFrame()
        completed_tasks = len(completed_df)
        pending_df = active_df[active_df["status"] == "PENDING"] if not active_df.empty else pd.DataFrame()
        pending_tasks = len(pending_df)
        
        workers = active_df["worker_name"].dropna().unique() if not active_df.empty else []
        active_workers = len(workers)
        avg_hours_per_worker = (total_hours / active_workers) if active_workers > 0 else 0.0
        
        night_tasks_count = int(active_df["is_night_work"].sum()) if not active_df.empty else 0
        weekend_tasks_count = int(active_df["is_weekend_work"].sum()) if not active_df.empty else 0
        
        # 예정 시간 초과 건수
        if not active_df.empty:
            overdue_mask = (active_df["status"] == "COMPLETED") & (active_df["actual_minutes"] > active_df["estimated_minutes"]) & (active_df["estimated_minutes"] > 0)
            overdue_tasks_count = int(overdue_mask.sum())
        else:
            overdue_tasks_count = 0
        overdue_rate = (overdue_tasks_count / completed_tasks * 100.0) if completed_tasks > 0 else 0.0

        return {
            "total_hours": round(total_hours, 1),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": pending_tasks,
            "active_workers": active_workers,
            "avg_hours_per_worker": round(avg_hours_per_worker, 1),
            "night_tasks_count": night_tasks_count,
            "weekend_tasks_count": weekend_tasks_count,
            "overdue_tasks_count": overdue_tasks_count,
            "overdue_rate": round(overdue_rate, 1),
        }

    @staticmethod
    def get_worker_summary(df: pd.DataFrame) -> pd.DataFrame:
        """
        팀원별 총 투입 시간, 건수, 평일주간/평일야간/주말 비중 집계
        (주말+야간은 주말로 통합 분류)
        """
        if df.empty:
            return pd.DataFrame()

        df_calc = df[df["status"].isin(["COMPLETED", "PENDING"])].copy() if "status" in df.columns else df.copy()
        if df_calc.empty:
            return pd.DataFrame()

        df_calc["is_weekend_flag"] = df_calc["is_weekend_work"] == True
        df_calc["is_weekday_night_flag"] = (df_calc["is_weekend_work"] == False) & (df_calc["is_night_work"] == True)
        df_calc["is_weekday_day_flag"] = (df_calc["is_weekend_work"] == False) & (df_calc["is_night_work"] == False)

        summary = df_calc.groupby("worker_name").agg(
            total_hours=("actual_hours", "sum"),
            total_tasks=("id", "count") if "id" in df_calc.columns else ("worker_name", "count"),
            weekend_tasks=("is_weekend_flag", "sum"),
            weekday_night_tasks=("is_weekday_night_flag", "sum"),
            weekday_day_tasks=("is_weekday_day_flag", "sum"),
            night_tasks=("is_night_work", "sum"),
            avg_hours=("actual_hours", "mean"),
            team=("worker_team", "first") if "worker_team" in df_calc.columns else ("worker_name", lambda x: ""),
            title=("worker_title", "first") if "worker_title" in df_calc.columns else ("worker_name", lambda x: "")
        ).reset_index()

        summary["total_hours"] = summary["total_hours"].round(1)
        summary["avg_hours"] = summary["avg_hours"].round(1)
        summary = summary.sort_values(by="total_hours", ascending=False)
        return summary

    @staticmethod
    def get_monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
        """
        월별 총 투입 시간 및 작업 건수 추이
        """
        if df.empty:
            return pd.DataFrame()

        target_df = df[df["status"].isin(["COMPLETED", "PENDING"])] if "status" in df.columns else df
        if target_df.empty:
            return pd.DataFrame()

        trend = target_df.groupby("month_str").agg(
            total_hours=("actual_hours", "sum"),
            total_tasks=("id", "count") if "id" in target_df.columns else ("month_str", "count"),
            night_tasks=("is_night_work", "sum"),
            worker_count=("worker_name", "nunique")
        ).reset_index()

        trend["total_hours"] = trend["total_hours"].round(1)
        trend = trend.sort_values(by="month_str")
        return trend

    @staticmethod
    def get_client_summary(df: pd.DataFrame) -> pd.DataFrame:
        """
        고객사별 투입 시간 및 비중 집계
        """
        if df.empty:
            return pd.DataFrame()

        target_df = df[df["status"].isin(["COMPLETED", "PENDING"])] if "status" in df.columns else df
        if target_df.empty:
            return pd.DataFrame()

        client_df = target_df.groupby("client_name").agg(
            total_hours=("actual_hours", "sum"),
            total_tasks=("id", "count") if "id" in target_df.columns else ("client_name", "count"),
            worker_count=("worker_name", "nunique")
        ).reset_index()

        total_all_hours = client_df["total_hours"].sum()
        if total_all_hours > 0:
            client_df["ratio_pct"] = ((client_df["total_hours"] / total_all_hours) * 100).round(1)
        else:
            client_df["ratio_pct"] = 0.0

        client_df["total_hours"] = client_df["total_hours"].round(1)
        client_df = client_df.sort_values(by="total_hours", ascending=False)
        return client_df

    @staticmethod
    def get_type_summary(df: pd.DataFrame) -> pd.DataFrame:
        """
        작업 구분별(작업/지원/점검/장애 등) 집계
        """
        if df.empty:
            return pd.DataFrame()

        target_df = df[df["status"].isin(["COMPLETED", "PENDING"])] if "status" in df.columns else df
        if target_df.empty:
            return pd.DataFrame()

        type_df = target_df.groupby("log_type").agg(
            total_hours=("actual_hours", "sum"),
            total_tasks=("id", "count") if "id" in target_df.columns else ("log_type", "count")
        ).reset_index()

        type_df["total_hours"] = type_df["total_hours"].round(1)
        type_df = type_df.sort_values(by="total_hours", ascending=False)
        return type_df
