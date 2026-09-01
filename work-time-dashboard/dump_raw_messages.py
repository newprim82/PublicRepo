import sys
import sqlite3
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.config import config

conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
cursor = conn.cursor()

cursor.execute("""
    SELECT id, msg_hash, start_time, end_time, status, worker_name, client_name, task_description, estimated_minutes, actual_minutes, raw_start_message, raw_end_message
    FROM work_logs
    WHERE client_name LIKE '%한화%' AND task_description LIKE '%VPN%'
    ORDER BY start_time DESC
""")

rows = cursor.fetchall()
print(f"조회된 레코드 수: {len(rows)}건\n")

for row in rows:
    print(f"ID: {row[0]}")
    print(f"msg_hash: {row[1]}")
    print(f"start_time: {row[2]}")
    print(f"end_time: {row[3]}")
    print(f"status: {row[4]}")
    print(f"worker_name: {row[5]}")
    print(f"client_name: {row[6]}")
    print(f"task_desc: {row[7]}")
    print(f"estimated_minutes: {row[8]}")
    print(f"actual_minutes: {row[9]}")
    print(f"raw_start_message: {repr(row[10])}")
    print(f"raw_end_message: {repr(row[11])}")
    print("-" * 50)

conn.close()
