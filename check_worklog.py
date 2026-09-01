import sqlite3
from pathlib import Path

conn = sqlite3.connect(r"c:\Python\work-time-dashboard\data\worklog.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT count(*) FROM work_logs
""")
cnt = cursor.fetchone()[0]
print(f"현재 worklog.db의 총 레코드 수: {cnt}건")

cursor.execute("""
    SELECT id, msg_hash, start_time, end_time, status, worker_name, client_name, task_description, estimated_minutes, actual_minutes, raw_start_message, raw_end_message
    FROM work_logs
    ORDER BY id DESC
    LIMIT 20
""")

rows = cursor.fetchall()
for row in rows:
    print(f"[{row[4]}] {row[2]} ~ {row[3]} | {row[5]} | {row[6]} | {row[7]} | 예정:{row[8]/60}h, 소요:{row[9]/60}h")
    print(f"  시작: {repr(row[10])}")
    print(f"  완료: {repr(row[11])}\n")

conn.close()
