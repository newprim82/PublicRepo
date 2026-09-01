import sqlite3
from pathlib import Path

conn = sqlite3.connect(r"c:\Python\work-time-dashboard\data\work_logs.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT start_time, end_time, status, worker_name, client_name, task_description, estimated_minutes, actual_minutes, raw_start_message, raw_end_message
    FROM work_logs
    WHERE start_time LIKE '2026-07-27%' OR start_time LIKE '2026-07-28%'
    ORDER BY start_time ASC
""")

rows = cursor.fetchall()
print(f"7월 27일~28일 레코드 수: {len(rows)}건\n")

for row in rows:
    print(f"[{row[2]}] {row[0]} ~ {row[1]} | {row[3]} | {row[4]} | {row[5]} | 예정:{row[6]/60}h, 소요:{row[7]/60}h")
    print(f"  시작: {repr(row[8])}")
    print(f"  완료: {repr(row[9])}\n")

conn.close()
