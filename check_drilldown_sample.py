import sys
import pandas as pd
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.database.supabase_client import db_manager

df = db_manager.fetch_all_work_logs()

# 전종필의 2026-04 데이터 또는 4월 1주차 데이터 조회
jp_df = df[(df["worker_name"].str.contains("전종필")) & (df["month_str"] == "2026-04")]
print(f"전종필 2026-04 작업 건수: {len(jp_df)}건")
print("\n[주차별 시간 집계]:")
print(jp_df.groupby("week_label")["actual_hours"].sum())

print("\n[2026-04 1주차 상세 내역]:")
w1_df = jp_df[jp_df["week_label"].str.contains("1주차")]
print(w1_df[["start_time", "client_name", "task_description", "actual_hours", "status", "raw_start_message"]].to_string())
