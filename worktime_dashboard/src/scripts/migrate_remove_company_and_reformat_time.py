"""
로컬 SQLite (data/worklog.db) 마이그레이션 스크립트:
1. worker_company 컬럼 제거
2. start_time 및 end_time을 'YYYY-MM-DD HH:MM' (초와 +00 타임존 제외) 포맷으로 일괄 변환
"""

import os
import sys
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

# 프로젝트 루트 경로 설정
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "worklog.db"
BACKUP_DIR = PROJECT_ROOT / "backup"

def migrate():
    print("==================================================")
    print("🚀 [로컬 SQLite 스키마 및 시간 포맷 마이그레이션 시작]")
    print("==================================================")

    if not DB_PATH.exists():
        print(f"[!] {DB_PATH} 파일이 존재하지 않아 마이그레이션을 건너뜁니다.")
        return

    # 1. 원본 백업
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"worklog_backup_before_schema_update_{ts}.db"
    shutil.copy2(DB_PATH, backup_file)
    print(f"[✅ 백업 완료] {backup_file.name}")

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 2. 임시 새 테이블 생성 (worker_company 없음)
    cursor.execute("""
        CREATE TABLE work_logs_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_hash TEXT UNIQUE NOT NULL,
            log_type TEXT,
            worker_name TEXT NOT NULL,
            worker_title TEXT,
            worker_team TEXT,
            client_name TEXT NOT NULL,
            task_description TEXT NOT NULL,
            estimated_minutes INTEGER DEFAULT 0,
            actual_minutes INTEGER DEFAULT 0,
            start_time TEXT NOT NULL,
            end_time TEXT,
            status TEXT DEFAULT 'COMPLETED',
            is_night_work INTEGER DEFAULT 0,
            is_weekend_work INTEGER DEFAULT 0,
            raw_start_message TEXT,
            raw_end_message TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 3. 기존 데이터 조회 및 변환 이관
    cursor.execute("SELECT * FROM work_logs")
    old_rows = cursor.fetchall()
    
    # 컬럼 인덱스 매핑
    cursor.execute("PRAGMA table_info(work_logs)")
    old_cols = [r[1] for r in cursor.fetchall()]
    col_idx = {name: i for i, name in enumerate(old_cols)}

    migrated_count = 0
    for row in old_rows:
        msg_hash = row[col_idx["msg_hash"]]
        log_type = row[col_idx["log_type"]]
        worker_name = row[col_idx["worker_name"]]
        worker_title = row[col_idx["worker_title"]] if "worker_title" in col_idx else ""
        worker_team = row[col_idx["worker_team"]] if "worker_team" in col_idx else ""
        client_name = row[col_idx["client_name"]]
        task_description = row[col_idx["task_description"]]
        estimated_minutes = row[col_idx["estimated_minutes"]]
        actual_minutes = row[col_idx["actual_minutes"]]
        
        # start_time, end_time 16자리 (YYYY-MM-DD HH:MM) 포맷으로 변환
        raw_start = str(row[col_idx["start_time"]] or "")
        start_time_clean = raw_start.replace("T", " ")[:16]

        raw_end = row[col_idx["end_time"]]
        end_time_clean = (str(raw_end).replace("T", " ")[:16]) if raw_end else None

        status = row[col_idx["status"]]
        is_night_work = row[col_idx["is_night_work"]]
        is_weekend_work = row[col_idx["is_weekend_work"]]
        raw_start_message = row[col_idx["raw_start_message"]]
        raw_end_message = row[col_idx["raw_end_message"]]
        created_at = row[col_idx["created_at"]] if "created_at" in col_idx else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT OR IGNORE INTO work_logs_new (
                msg_hash, log_type, worker_name, worker_title, worker_team,
                client_name, task_description, estimated_minutes, actual_minutes,
                start_time, end_time, status, is_night_work, is_weekend_work,
                raw_start_message, raw_end_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            msg_hash, log_type, worker_name, worker_title, worker_team,
            client_name, task_description, estimated_minutes, actual_minutes,
            start_time_clean, end_time_clean, status, is_night_work, is_weekend_work,
            raw_start_message, raw_end_message, created_at
        ))
        migrated_count += 1

    # 4. 기존 테이블 삭제 및 교체
    cursor.execute("DROP TABLE work_logs")
    cursor.execute("ALTER TABLE work_logs_new RENAME TO work_logs")
    conn.commit()
    conn.close()

    print(f"[✅ 마이그레이션 성공] 총 {migrated_count}건 이관 완료 (worker_company 제거 및 분 단위 시간 적용)")

if __name__ == "__main__":
    migrate()
