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
    Supabase 클라우드 DB & 로컬 SQLite 하이브리드 데이터베이스 매니저
    - Supabase 설정 시: 다중 PC 실시간 클라우드 동기화 (우선) + 로컬 백업
    - Supabase 미설정 시: 로컬 SQLite 단독 모드
    """
    
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.use_supabase = False
        self._init_connection()
        self._init_local_db()

    def _init_connection(self):
        """Supabase 클라우드 연결 초기화"""
        if config.is_supabase_configured() and Client is not None:
            try:
                self.supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
                self.use_supabase = True
                print("[DB] Supabase Cloud DB connected successfully. (Multi-PC Real-Time Sync Mode)")
            except Exception as e:
                print(f"[DB Warning] Supabase connection failed: {e}. Fallback to local SQLite.")
                self.use_supabase = False
        else:
            print("[DB Info] Supabase not configured. Running in local SQLite mode.")
            self.use_supabase = False

    def _init_local_db(self):
        """로컬 SQLite 테이블 초기화 (오프라인 백업 및 캐시용)"""
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
        데이터베이스 전체 초기화
        """
        success = True
        if self.use_supabase and self.supabase:
            try:
                self.supabase.table("work_logs").delete().neq("id", 0).execute()
                print("[DB] ☁️ Supabase work_logs 데이터 전체 삭제 완료")
            except Exception as e:
                print(f"[DB 오류] Supabase 데이터 삭제 실패: {e}")
                success = False

        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM work_logs")
            conn.commit()
            conn.close()
            print("[DB] 💾 로컬 SQLite 데이터 전체 삭제 완료")
        except Exception as e:
            print(f"[DB 오류] 로컬 SQLite 데이터 삭제 실패: {e}")
            success = False

        return success

    def save_work_logs(self, records: List[WorkLogRecord]) -> int:
        """
        파싱된 WorkLogRecord 리스트를 Supabase(클라우드) 및 로컬 SQLite에 동시 Upsert 저장
        """
        if not records:
            return 0

        # 1. Supabase 클라우드 DB 저장
        if self.use_supabase and self.supabase:
            try:
                payloads = []
                for r in records:
                    payloads.append({
                        "msg_hash": r.msg_hash,
                        "log_type": r.log_type,
                        "worker_name": r.worker_name,
                        "worker_company": r.worker_company,
                        "worker_title": r.worker_title,
                        "worker_team": r.worker_team,
                        "client_name": r.client_name,
                        "task_description": r.task_description,
                        "estimated_minutes": r.estimated_minutes,
                        "actual_minutes": r.actual_minutes,
                        "start_time": r.start_time.isoformat(),
                        "end_time": r.end_time.isoformat() if r.end_time else None,
                        "status": r.status,
                        "is_night_work": r.is_night_work,
                        "is_weekend_work": r.is_weekend_work,
                        "raw_start_message": r.raw_start_message,
                        "raw_end_message": r.raw_end_message
                    })
                
                # 100개 단위 배치 Upsert
                for i in range(0, len(payloads), 100):
                    batch = payloads[i:i+100]
                    self.supabase.table("work_logs").upsert(batch, on_conflict="msg_hash").execute()
                print(f"[DB] ☁️ Supabase에 {len(records)}건 Upsert 완료")
            except Exception as e:
                print(f"[DB 오류] Supabase 저장 실패 (로컬 DB 백업 유지): {e}")

        # 2. 로컬 SQLite 백업 저장
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
        Supabase 클라우드 DB에서 전체 데이터를 최우선 조회 (오프라인 시 로컬 SQLite 조회)
        """
        if self.use_supabase and self.supabase:
            try:
                # Supabase 페이지네이션을 통해 10,000건 이상도 전수 조회
                all_data = []
                page_size = 1000
                start = 0
                while True:
                    res = self.supabase.table("work_logs")\
                        .select("*")\
                        .order("start_time", desc=True)\
                        .range(start, start + page_size - 1)\
                        .execute()
                    rows = res.data or []
                    all_data.extend(rows)
                    if len(rows) < page_size:
                        break
                    start += page_size
                    
                df = pd.DataFrame(all_data)

                # 💾 로컬 SQLite 오프라인 백업 DB에도 최신 데이터 자동 동기화
                if not df.empty:
                    self._sync_to_local_sqlite(df)

                return self._process_dataframe(df)
            except Exception as e:
                print(f"[DB 오류] Supabase 조회 실패, 로컬 SQLite로 대체: {e}")

        # 로컬 SQLite Fallback
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            df = pd.read_sql_query("SELECT * FROM work_logs ORDER BY start_time DESC", conn)
            conn.close()
            return self._process_dataframe(df)
        except Exception as e:
            print(f"[DB 오류] SQLite 데이터 조회 실패: {e}")
            return self._process_dataframe(pd.DataFrame())

    def _sync_to_local_sqlite(self, df: pd.DataFrame):
        """Supabase에서 조회한 최신 데이터를 로컬 SQLite에 안전하게 동기화"""
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            for _, r in df.iterrows():
                msg_hash = r.get("msg_hash", "")
                if not msg_hash:
                    continue
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
                    str(msg_hash), str(r.get("log_type", "작업")), str(r.get("worker_name", "")),
                    str(r.get("worker_company", "")), str(r.get("worker_title", "")), str(r.get("worker_team", "")),
                    str(r.get("client_name", "")), str(r.get("task_description", "")),
                    int(r.get("estimated_minutes", 0) or 0), int(r.get("actual_minutes", 0) or 0),
                    str(r.get("start_time", "")), str(r.get("end_time", "") or ""),
                    str(r.get("status", "COMPLETED")),
                    1 if r.get("is_night_work") else 0,
                    1 if r.get("is_weekend_work") else 0,
                    str(r.get("raw_start_message", "") or ""),
                    str(r.get("raw_end_message", "") or "")
                ))
            conn.commit()
            conn.close()
        except Exception:
            pass

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
