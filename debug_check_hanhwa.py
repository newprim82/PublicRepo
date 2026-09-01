import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.database.supabase_client import db_manager

df = db_manager.fetch_all_work_logs()
hanhwa = df[df["client_name"].str.contains("한화", na=False)]
print(f"[한화 관련 레코드 총 {len(hanhwa)}건]:")
for idx, r in hanhwa.iterrows():
    print(f"[{r['status']}] {r['start_time']} | {r['worker_name']} | {r['client_name']} | {r['task_description']} | 예정: {r['estimated_hours']}h | 소요: {r['actual_hours']}h")
    print(f"  시작 메시지: {repr(r['raw_start_message'])}")
    print(f"  완료 메시지: {repr(r['raw_end_message'])}\n")
