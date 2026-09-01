import sys
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.config import config
from src.database.supabase_client import db_manager

print("[DB 내 48시간 초과 PENDING 데이터 자동 완료 마이그레이션 시작]")

conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
cursor = conn.cursor()

cursor.execute("""
    SELECT id, msg_hash, worker_name, start_time, estimated_minutes
    FROM work_logs
    WHERE status = 'PENDING'
""")
pending_rows = cursor.fetchall()
print(f"조회된 PENDING 건수: {len(pending_rows)}건")

updated_count = 0
now = datetime.now()

for row in pending_rows:
    row_id, msg_hash, worker_name, start_time_str, est_mins = row
    try:
        if "+" in start_time_str:
            st_dt = datetime.fromisoformat(start_time_str.split("+")[0])
        elif "Z" in start_time_str:
            st_dt = datetime.fromisoformat(start_time_str.replace("Z", ""))
        else:
            st_dt = datetime.fromisoformat(start_time_str)
    except:
        continue
        
    if (now - st_dt).total_seconds() >= 48 * 3600:
        actual = est_mins if est_mins and est_mins > 0 else 60
        end_dt = st_dt + timedelta(minutes=actual)
        end_time_str = end_dt.isoformat()
        
        cursor.execute("""
            UPDATE work_logs
            SET status = 'COMPLETED',
                actual_minutes = ?,
                end_time = ?,
                raw_end_message = '[자동완료] 48시간 경과로 시작보고 기준 완료 처리'
            WHERE id = ?
        """, (actual, end_time_str, row_id))
        
        if db_manager.use_supabase and db_manager.supabase:
            try:
                db_manager.supabase.table("work_logs").update({
                    "status": "COMPLETED",
                    "actual_minutes": actual,
                    "end_time": end_time_str,
                    "raw_end_message": "[자동완료] 48시간 경과로 시작보고 기준 완료 처리"
                }).eq("msg_hash", msg_hash).execute()
            except Exception as e:
                pass
                
        updated_count += 1

conn.commit()
conn.close()

print(f"[성공] 총 {updated_count}건의 48시간 경과 PENDING 건이 '시작보고(예정시간) 기준 완료(COMPLETED)'로 정상 전환되었습니다!")
