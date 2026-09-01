import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime

from ..config import config
from ..parser.reply_matcher import WorkLogRecord


class DatabaseManager:
    """
    로컬 SQLite 기반 고성능 데이터베이스 매니저 (Supabase 의존성 완전 제거)
    """
    
    def __init__(self):
        self._init_local_db()

    def _init_local_db(self):
        """로컬 SQLite 테이블 초기화"""
        db_path = config.LOCAL_DB_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS work_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                msg_hash TEXT UNIQUE NOT NULL,
                log_type TEXT,
                worker_name TEXT NOT NULL,
                worker_company TEXT,
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
        conn.commit()
        conn.close()

    def clear_all_data(self) -> bool:
        """
        데이터베이스 전체 초기화 (재적재 필요 시 사용)
        """
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM work_logs")
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[DB 오류] 로컬 SQLite 데이터 삭제 실패: {e}")
            return False

    def save_work_logs(self, records: List[WorkLogRecord]) -> int:
        """
        파싱된 WorkLogRecord 리스트를 로컬 SQLite DB에 Upsert 저장
        """
        if not records:
            return 0

        saved_count = 0
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            for r in records:
                cursor.execute("""
                    INSERT INTO work_logs (
                        msg_hash, log_type, worker_name, worker_company, worker_title, worker_team,
                        client_name, task_description, estimated_minutes, actual_minutes,
                        start_time, end_time, status, is_night_work, is_weekend_work,
                        raw_start_message, raw_end_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(msg_hash) DO UPDATE SET
                        actual_minutes=excluded.actual_minutes,
                        end_time=excluded.end_time,
                        status=excluded.status,
                        is_night_work=excluded.is_night_work,
                        raw_end_message=excluded.raw_end_message
                """, (
                    r.msg_hash, r.log_type, r.worker_name, r.worker_company, r.worker_title, r.worker_team,
                    r.client_name, r.task_description, r.estimated_minutes, r.actual_minutes,
                    r.start_time.isoformat(), r.end_time.isoformat() if r.end_time else None,
                    r.status, 1 if r.is_night_work else 0, 1 if r.is_weekend_work else 0,
                    r.raw_start_message, r.raw_end_message
                ))
            conn.commit()
            conn.close()
            saved_count = len(records)
        except Exception as e:
            print(f"[DB 오류] 로컬 SQLite 저장 실패: {e}")

        return saved_count

    def fetch_all_work_logs(self) -> pd.DataFrame:
        """
        로컬 SQLite에서 전체 데이터 반환
        """
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            df = pd.read_sql_query("SELECT * FROM work_logs ORDER BY start_time DESC", conn)
            conn.close()
            return self._process_dataframe(df)
        except Exception as e:
            print(f"[DB 오류] SQLite 데이터 조회 실패: {e}")
            return self._process_dataframe(pd.DataFrame())

    def _process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=[
                "id", "msg_hash", "log_type", "worker_name", "worker_company", "worker_title", "worker_team",
                "client_name", "task_description", "estimated_minutes", "actual_minutes",
                "start_time", "end_time", "status", "is_night_work", "is_weekend_work",
                "actual_hours", "estimated_hours", "month_str", "date_str", "week_str", "week_label"
            ])
        
        df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
        if "end_time" in df.columns:
            df["end_time"] = pd.to_datetime(df["end_time"], errors="coerce")
            
        df["actual_minutes"] = pd.to_numeric(df.get("actual_minutes", 0), errors="coerce").fillna(0).astype(int)
        df["estimated_minutes"] = pd.to_numeric(df.get("estimated_minutes", 0), errors="coerce").fillna(0).astype(int)
        
        df["actual_hours"] = (df["actual_minutes"] / 60.0).round(1)
        df["estimated_hours"] = (df["estimated_minutes"] / 60.0).round(1)
        
        valid_dates = df["start_time"].dropna()
        if not valid_dates.empty:
            df["month_str"] = df["start_time"].dt.strftime("%Y-%m")
            df["date_str"] = df["start_time"].dt.strftime("%Y-%m-%d")
            
            # 주차 레이블 생성
            def get_week_label(dt):
                if pd.isna(dt):
                    return "미정"
                month = dt.month
                week_num = (dt.day - 1) // 7 + 1
                return f"{dt.strftime('%Y-%m')} {week_num}주차"
                
            df["week_label"] = df["start_time"].apply(get_week_label)
            df["week_str"] = df["start_time"].dt.strftime("%Y-%U주")
        else:
            df["month_str"] = "2026-08"
            df["date_str"] = "2026-08-01"
            df["week_label"] = "2026-08 1주차"
            df["week_str"] = "2026-31주"

        df["is_night_work"] = df.get("is_night_work", 0).astype(bool)
        df["is_weekend_work"] = df.get("is_weekend_work", 0).astype(bool)
        
        return df


db_manager = DatabaseManager()
