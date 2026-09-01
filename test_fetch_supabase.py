import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.database.supabase_client import db_manager

df = db_manager.fetch_all_work_logs()
print(f"Supabase 클라우드에서 조회된 레코드 수: {len(df)}건")
print(f"use_supabase 상태: {db_manager.use_supabase}")

# 7월 한화 VPN 실사 확인
hanhwa = df[df["client_name"].str.contains("한화", na=False) & df["task_description"].str.contains("VPN", na=False)]
print(f"\n[Supabase 상 한화 VPN 실사 데이터]:")
for idx, r in hanhwa.iterrows():
    print(f"  [{r['status']}] {r['start_time']} | {r['worker_name']} | {r['client_name']} | 예정: {r['estimated_hours']}h | 소요: {r['actual_hours']}h")
