import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime

from ..config import config
from ..parser.reply_matcher import WorkLogRecord

try:
    from supabase import create_client, Client
except ImportError:
    Client = None

class DatabaseManager:
    """
    Supabase 및 로컬 SQLite를 지원하는 통합 데이터베이스 매니저
    """
    
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.use_supabase = False
        self._init_connection()
        self._init_local_db()

    def _init_connection(self):
        if config.is_supabase_configured() and Client is not None:
            try:
                self.supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
                self.use_supabase = True
                print("[DB] Supabase 클라이언트에 성공적으로 연결되었습니다.")
            except Exception as e:
                print(f"[DB 경고] Supabase 연결 실패: {e}. 로컬 SQLite로 전환합니다.")
                self.use_supabase = False
        else:
            print("[DB 알림] Supabase 설정이 비어있어 로컬 SQLite 모드로 동작합니다.")
            self.use_supabase = False

    def _init_local_db(self):
        """로컬 SQLite 테이블 초기화 (Supabase 미연결 또는 백업용)"""
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
        success = True
        if self.use_supabase and self.supabase:
            try:
                self.supabase.table("work_logs").delete().neq("id", 0).execute()
            except Exception as e:
                print(f"[DB 오류] Supabase 데이터 삭제 실패: {e}")
                success = False

        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM work_logs")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB 오류] 로컬 SQLite 데이터 삭제 실패: {e}")
            success = False
            
        return success

    def save_work_logs(self, records: List[WorkLogRecord]) -> int:
        """
        파싱된 WorkLogRecord 리스트를 Supabase 및 로컬 DB에 Upsert 저장
        """
        if not records:
            return 0

        saved_count = 0
        
        # 1. Supabase 저장 시도 (배치 100건 단위 분할 전송)
        if self.use_supabase and self.supabase:
            try:
                payloads = []
                for r in records:
                    item = r.to_dict()
                    payloads.append(item)
                
                batch_size = 100
                for i in range(0, len(payloads), batch_size):
                    batch = payloads[i:i+batch_size]
                    self.supabase.table("work_logs").upsert(batch, on_conflict="msg_hash").execute()
                    
                saved_count = len(payloads)
                print(f"[DB] Supabase에 {saved_count}건 저장/업데이트 완료.")
            except Exception as e:
                print(f"[DB 오류] Supabase 저장 중 예외 발생: {e}. 로컬 DB에 기록합니다.")

        # 2. 로컬 SQLite에도 동기화 저장
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
            if not self.use_supabase:
                saved_count = len(records)
        except Exception as e:
            print(f"[DB 오류] 로컬 SQLite 저장 실패: {e}")

        return saved_count

    def fetch_all_work_logs(self) -> pd.DataFrame:
        """
        Supabase(페이징 전수 조회) 또는 로컬 SQLite에서 전체 데이터 반환
        """
        if self.use_supabase and self.supabase:
            try:
                all_rows = []
                page_size = 1000
                start = 0
                while True:
                    res = self.supabase.table("work_logs").select("*").order("start_time", desc=True).range(start, start + page_size - 1).execute()
                    if not res.data:
                        break
                    all_rows.extend(res.data)
                    if len(res.data) < page_size:
                        break
                    start += page_size

                if all_rows:
                    df = pd.DataFrame(all_rows)
                    return self._process_dataframe(df)
            except Exception as e:
                print(f"[DB 오류] Supabase 조회 실패: {e}. 로컬 DB에서 조회합니다.")

        conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
        df = pd.read_sql_query("SELECT * FROM work_logs ORDER BY start_time DESC", conn)
        conn.close()
        
        return self._process_dataframe(df)

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
        
        df["month_str"] = df["start_time"].dt.strftime("%Y-%m")
        df["date_str"] = df["start_time"].dt.strftime("%Y-%m-%d")
        
        # 주차(Week) 계산: ISO 주차 및 주간 범위 레이블 (월요일~일요일)
        def get_week_label(dt):
            if pd.isna(dt):
                return ""
            from datetime import timedelta
            # 해당 날짜가 속한 주의 월요일 & 일요일
            mon = dt - timedelta(days=dt.weekday())
            sun = mon + timedelta(days=6)
            # 월 기준 주차 계산 (월요일 기준)
            week_of_month = (mon.day - 1) // 7 + 1
            return f"{mon.strftime('%Y-%m')} {week_of_month}주차 ({mon.strftime('%m/%d')}~{sun.strftime('%m/%d')})"

        df["week_str"] = df["start_time"].dt.strftime("%G-W%V")
        df["week_label"] = df["start_time"].apply(get_week_label)
        
        df["is_night_work"] = df["is_night_work"].astype(bool)
        df["is_weekend_work"] = df["is_weekend_work"].astype(bool)
        
        return df

db_manager = DatabaseManager()
