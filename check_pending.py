import sys
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.database.supabase_client import db_manager

df = db_manager.fetch_all_work_logs()
pending_df = df[df["status"] == "PENDING"]
print(f"전체 레코드: {len(df)}건 중 PENDING 건수: {len(pending_df)}건")

if not pending_df.empty:
    print("PENDING 데이터 샘플(상위 10개):")
    print(pending_df[["start_time", "worker_name", "client_name", "task_description", "estimated_minutes", "actual_minutes"]].head(10))
