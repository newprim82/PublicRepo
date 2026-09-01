import sqlite3
from typing import Dict, Optional
from datetime import datetime
import pandas as pd

from ..config import config

class RewardLeaveService:
    @staticmethod
    def init_table():
        """로컬 SQLite에 reward_leave_logs 테이블 생성"""
        conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reward_leave_logs (
                worker_name TEXT NOT NULL,
                week_label TEXT NOT NULL,
                leave_hours REAL DEFAULT 0,
                note TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                PRIMARY KEY (worker_name, week_label)
            )
        """)
        conn.commit()
        conn.close()

    @staticmethod
    def get_all_reward_leaves() -> Dict[tuple, dict]:
        """모든 보상 휴가 기록을 딕셔너리로 반환 {(worker_name, week_label): {'leave_hours': 8.0, 'note': '대휴 1일'}}"""
        RewardLeaveService.init_table()
        leaves = {}

        conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT worker_name, week_label, leave_hours, note, updated_at FROM reward_leave_logs")
        for row in cursor.fetchall():
            key = (row[0], row[1])
            leaves[key] = {
                "leave_hours": float(row[2] or 0),
                "note": row[3] or "",
                "updated_at": row[4] or ""
            }
        conn.close()
        return leaves

    @staticmethod
    def get_reward_leave(worker_name: str, week_label: str) -> Optional[dict]:
        """특정 작업자 및 주차의 보상 휴가 기록 조회"""
        leaves = RewardLeaveService.get_all_reward_leaves()
        return leaves.get((worker_name, week_label))

    @staticmethod
    def save_reward_leave(worker_name: str, week_label: str, leave_hours: float, note: str):
        """보상 휴가 등록 또는 수정"""
        RewardLeaveService.init_table()

        conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reward_leave_logs (worker_name, week_label, leave_hours, note, updated_at)
            VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(worker_name, week_label) DO UPDATE SET
                leave_hours=excluded.leave_hours,
                note=excluded.note,
                updated_at=excluded.updated_at
        """, (worker_name, week_label, leave_hours, note))
        conn.commit()
        conn.close()

    @staticmethod
    def delete_reward_leave(worker_name: str, week_label: str):
        """보상 휴가 삭제 (미부여 상태로 복구)"""
        RewardLeaveService.init_table()

        conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reward_leave_logs WHERE worker_name=? AND week_label=?", (worker_name, week_label))
        conn.commit()
        conn.close()
