import sqlite3
import time
from typing import Dict, Optional
from datetime import datetime
import pandas as pd

from ..config import config
from ..database.supabase_client import db_manager

class RewardLeaveService:
    # ⚡ [인메모리 캐시] 사용자 PC의 RAM에 보관하여 Supabase 반복 네트워크 호출(1회당 200~400ms)을 0ms로 단축
    _reward_leaves_cache: Optional[Dict[tuple, dict]] = None
    _cache_time: float = 0.0
    CACHE_TTL: float = 60.0  # 60초 유효시간 (데이터 변경 시 즉시 무효화)

    @classmethod
    def clear_cache(cls):
        """인메모리 캐시 초기화 (보상 휴가 등록/수정/삭제 시 즉시 호출)"""
        cls._reward_leaves_cache = None
        cls._cache_time = 0.0

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

    @classmethod
    def get_all_reward_leaves(cls) -> Dict[tuple, dict]:
        """모든 보상 휴가 기록을 딕셔너리로 반환 (RAM 캐싱으로 Supabase 네트워크 지연 0ms 제거)"""
        now = time.time()
        if cls._reward_leaves_cache is not None and (now - cls._cache_time < cls.CACHE_TTL):
            return dict(cls._reward_leaves_cache)

        cls.init_table()
        leaves = {}

        # 1. Supabase 조회 시도
        if db_manager.use_supabase and db_manager.supabase:
            try:
                res = db_manager.supabase.table("worktime_reward_leave_logs").select("*").execute()
                for row in (res.data or []):
                    key = (row["worker_name"], row["week_label"])
                    leaves[key] = {
                        "leave_hours": float(row.get("leave_hours") or 0),
                        "note": row.get("note") or "",
                        "updated_at": row.get("updated_at") or ""
                    }
                if leaves:
                    cls._reward_leaves_cache = dict(leaves)
                    cls._cache_time = now
                    return leaves
            except Exception as e:
                print(f"[Supabase 보상휴가 조회 알림]: {e}")

        # 2. 로컬 SQLite 조회
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

        cls._reward_leaves_cache = dict(leaves)
        cls._cache_time = now
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

        # 1. Supabase 저장
        if db_manager.use_supabase and db_manager.supabase:
            try:
                db_manager.supabase.table("worktime_reward_leave_logs").upsert({
                    "worker_name": worker_name,
                    "week_label": week_label,
                    "leave_hours": leave_hours,
                    "note": note
                }).execute()
            except Exception as e:
                print(f"[Supabase 보상휴가 저장 알림]: {e}")

        # 2. 로컬 SQLite 저장
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
        RewardLeaveService.clear_cache()

    @staticmethod
    def delete_reward_leave(worker_name: str, week_label: str):
        """보상 휴가 삭제 (미부여 상태로 복구)"""
        RewardLeaveService.init_table()

        # 1. Supabase 삭제
        if db_manager.use_supabase and db_manager.supabase:
            try:
                db_manager.supabase.table("worktime_reward_leave_logs")\
                    .delete()\
                    .eq("worker_name", worker_name)\
                    .eq("week_label", week_label)\
                    .execute()
            except Exception as e:
                print(f"[Supabase 보상휴가 삭제 알림]: {e}")

        # 2. 로컬 SQLite 삭제
        conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reward_leave_logs WHERE worker_name=? AND week_label=?", (worker_name, week_label))
        conn.commit()
        conn.close()
        RewardLeaveService.clear_cache()
