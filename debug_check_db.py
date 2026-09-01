import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.database.supabase_client import db_manager

df = db_manager.fetch_all_work_logs()
print(f"총 레코드 수: {len(df)}건")
if not df.empty:
    kims = df[df['worker_name'] == '김시우']
    print(f"\n[김시우 레코드 총 {len(kims)}건]:")
    print(kims[['start_time', 'status', 'client_name', 'task_description', 'estimated_hours', 'actual_hours', 'raw_start_message', 'raw_end_message']].head(10).to_string())
