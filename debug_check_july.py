import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.database.supabase_client import db_manager

df = db_manager.fetch_all_work_logs()
july27 = df[(df["worker_name"] == "김시우") & (df["start_time"].dt.month == 7)]
print(f"[김시우 7월 레코드 총 {len(july27)}건]:")
for idx, r in july27.iterrows():
    print(f"[{r['status']}] {r['start_time']} | {r['client_name']} | {r['task_description']} | 예정: {r['estimated_hours']}h | 소요: {r['actual_hours']}h")
    print(f"  시작 메시지: {repr(r['raw_start_message'])}")
    print(f"  완료 메시지: {repr(r['raw_end_message'])}\n")
