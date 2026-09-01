import sys
import sqlite3
import pandas as pd
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.config import config
from src.database.supabase_client import db_manager

# 1. 로컬 SQLite에서 최신 정제 데이터 읽기
conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
df = pd.read_sql_query("SELECT * FROM work_logs", conn)
conn.close()

print(f"로컬 DB 레코드 수: {len(df)}건")

if not df.empty:
    # 2. Supabase에 일괄 Upsert 업로드 (배치 처리)
    payloads = []
    for idx, r in df.iterrows():
        payloads.append({
            "msg_hash": r["msg_hash"],
            "log_type": r["log_type"],
            "worker_name": r["worker_name"],
            "worker_company": r["worker_company"],
            "worker_title": r["worker_title"],
            "worker_team": r["worker_team"],
            "client_name": r["client_name"],
            "task_description": r["task_description"],
            "estimated_minutes": int(r["estimated_minutes"]),
            "actual_minutes": int(r["actual_minutes"]),
            "start_time": r["start_time"],
            "end_time": r["end_time"] if pd.notna(r["end_time"]) else None,
            "status": r["status"],
            "is_night_work": bool(r["is_night_work"]),
            "is_weekend_work": bool(r["is_weekend_work"]),
            "raw_start_message": r["raw_start_message"],
            "raw_end_message": r["raw_end_message"]
        })

    # 100개 단위 배치 전송
    batch_size = 100
    total_uploaded = 0
    for i in range(0, len(payloads), batch_size):
        batch = payloads[i:i+batch_size]
        res = db_manager.supabase.table("work_logs").upsert(batch, on_conflict="msg_hash").execute()
        total_uploaded += len(batch)
        print(f"  [Supabase 업로드 진행] {total_uploaded}/{len(payloads)}건 완료...")

    print(f"\n[SUCCESS] Supabase 클라우드에 총 {total_uploaded}건의 작업 로그가 완벽히 업로드 동기화되었습니다!")

    # Supabase 조회 검증
    res = db_manager.supabase.table("work_logs").select("id", count="exact").execute()
    print(f"Supabase 클라우드 최종 저장 건수: {res.count}건")
