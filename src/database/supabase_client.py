import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime, timedelta

from ..config import config
from ..parser.reply_matcher import (
    WorkLogRecord,
    get_pending_timeout_hours,
    check_is_night_work,
    check_is_weekend_work
)
from ..parser.multiday_splitter import split_multiday_record, is_multiday_record
from .outlook_models import OutlookScheduleRecord

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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wl_start_time ON work_logs(start_time DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wl_status ON work_logs(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wl_worker ON work_logs(worker_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wl_client ON work_logs(client_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wl_worker_time ON work_logs(worker_name, start_time DESC)")

        # 📅 아웃룩 스케줄 테이블 생성 (로컬 백업 및 캐시용)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS outlook_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id TEXT UNIQUE NOT NULL,
                worker_name TEXT NOT NULL,
                worker_team TEXT DEFAULT '미배정',
                subject TEXT NOT NULL,
                schedule_type TEXT DEFAULT '작업',
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                duration_hours REAL DEFAULT 0.0,
                is_all_day INTEGER DEFAULT 0,
                is_leave INTEGER DEFAULT 0,
                leave_type TEXT,
                location TEXT,
                body TEXT,
                color_tag TEXT DEFAULT '#0284c7',
                created_by TEXT,
                synced_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_os_start_time ON outlook_schedules(start_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_os_worker ON outlook_schedules(worker_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_os_is_leave ON outlook_schedules(is_leave)")

        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        conn.commit()
        conn.close()

    def clear_all_data(self) -> bool:
        """
        데이터베이스 전체 초기화
        """
        success = True
        if self.use_supabase and self.supabase:
            try:
                self.supabase.table("worktime_work_logs").delete().neq("id", 0).execute()
                print("[DB] [Cloud] Supabase work_logs 데이터 전체 삭제 완료")
            except Exception as e:
                print(f"[DB 오류] Supabase 데이터 삭제 실패: {e}")
                success = False

        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM work_logs")
            conn.commit()
            conn.close()
            print("[DB] [Local] 로컬 SQLite 데이터 전체 삭제 완료")
        except Exception as e:
            print(f"[DB 오류] 로컬 SQLite 데이터 삭제 실패: {e}")
            success = False

        return success

    def save_work_logs(self, records: List[WorkLogRecord]) -> int:
        """
        파싱된 WorkLogRecord 리스트를 Supabase(클라우드) 및 로컬 SQLite에 동시 Upsert 저장
        (다일 작업 2days, 3days 등 감지 시 일자별 9.0시간 레코드로 자동 분할하여 저장)
        """
        if not records:
            return 0

        # 🌟 다일(Multi-day) 작업 자동 분할 (2days -> 일자별 9h씩 2건 전개)
        expanded_records: List[WorkLogRecord] = []
        for r in records:
            r_dict = r.to_dict()
            if is_multiday_record(r_dict):
                splits = split_multiday_record(r_dict)
                for s in splits:
                    st_p = pd.to_datetime(s["start_time"]).to_pydatetime()
                    ed_p = pd.to_datetime(s["end_time"]).to_pydatetime() if s.get("end_time") else None
                    expanded_records.append(WorkLogRecord(
                        msg_hash=s["msg_hash"],
                        log_type=s.get("log_type") or "작업",
                        worker_name=s.get("worker_name") or "",
                        worker_title=s.get("worker_title") or "",
                        worker_team=s.get("worker_team") or "",
                        client_name=s.get("client_name") or "",
                        task_description=s.get("task_description") or "",
                        estimated_minutes=int(s.get("estimated_minutes") or 540),
                        actual_minutes=int(s.get("actual_minutes") or 540),
                        start_time=st_p,
                        end_time=ed_p,
                        status=s.get("status") or "COMPLETED",
                        is_night_work=False,
                        is_weekend_work=bool(s.get("is_weekend_work")),
                        raw_start_message=str(s.get("raw_start_message") or ""),
                        raw_end_message=str(s.get("raw_end_message") or "")
                    ))
            else:
                expanded_records.append(r)
        records = expanded_records

        # 1. Supabase 클라우드 DB 저장
        if self.use_supabase and self.supabase:
            try:
                payloads = []
                for r in records:
                    st_str = r.start_time.strftime("%Y-%m-%d %H:%M") if hasattr(r.start_time, "strftime") else str(r.start_time)[:16]
                    ed_str = (r.end_time.strftime("%Y-%m-%d %H:%M") if hasattr(r.end_time, "strftime") else str(r.end_time)[:16]) if r.end_time else None
                    payloads.append({
                        "msg_hash": r.msg_hash,
                        "log_type": r.log_type,
                        "worker_name": r.worker_name,
                        "worker_title": r.worker_title,
                        "worker_team": r.worker_team,
                        "client_name": r.client_name,
                        "task_description": r.task_description,
                        "estimated_minutes": r.estimated_minutes,
                        "actual_minutes": r.actual_minutes,
                        "start_time": st_str,
                        "end_time": ed_str,
                        "status": r.status,
                        "is_night_work": r.is_night_work,
                        "is_weekend_work": r.is_weekend_work,
                        "raw_start_message": r.raw_start_message,
                        "raw_end_message": r.raw_end_message
                    })
                
                # 100개 단위 배치 Upsert
                for i in range(0, len(payloads), 100):
                    batch = payloads[i:i+100]
                    self.supabase.table("worktime_work_logs").upsert(batch, on_conflict="msg_hash").execute()
                print(f"[DB] [Cloud] Supabase에 {len(records)}건 Upsert 완료")
            except Exception as e:
                print(f"[DB 오류] Supabase 저장 실패 (로컬 DB 백업 유지): {e}")

        # 2. 로컬 SQLite 백업 저장
        saved_count = 0
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            for r in records:
                st_str = r.start_time.strftime("%Y-%m-%d %H:%M") if hasattr(r.start_time, "strftime") else str(r.start_time)[:16]
                ed_str = (r.end_time.strftime("%Y-%m-%d %H:%M") if hasattr(r.end_time, "strftime") else str(r.end_time)[:16]) if r.end_time else None
                cursor.execute("""
                    INSERT INTO work_logs (
                        msg_hash, log_type, worker_name, worker_title, worker_team,
                        client_name, task_description, estimated_minutes, actual_minutes,
                        start_time, end_time, status, is_night_work, is_weekend_work,
                        raw_start_message, raw_end_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(msg_hash) DO UPDATE SET
                        actual_minutes=excluded.actual_minutes,
                        end_time=excluded.end_time,
                        status=excluded.status,
                        is_night_work=excluded.is_night_work,
                        raw_end_message=excluded.raw_end_message
                """, (
                    r.msg_hash, r.log_type, r.worker_name, r.worker_title, r.worker_team,
                    r.client_name, r.task_description, r.estimated_minutes, r.actual_minutes,
                    st_str, ed_str,
                    r.status, 1 if r.is_night_work else 0, 1 if r.is_weekend_work else 0,
                    r.raw_start_message, r.raw_end_message
                ))
            conn.commit()
            conn.close()
            saved_count = len(records)
        except Exception as e:
            print(f"[DB 오류] 로컬 SQLite 저장 실패: {e}")

        return saved_count

    def resolve_expired_pending_tasks(self, df_source: Optional[pd.DataFrame] = None) -> int:
        """
        DB에 존재하는 PENDING(진행 중) 레코드 중 시작 시각으로부터
        48시간(다일 작업은 예정일수*24h + 48h)이 경과한 작업을
        시작 보고 기준 COMPLETED(완료)로 자동 승격하여 Supabase 및 로컬 DB에 영구 반영
        """
        try:
            if df_source is not None and not df_source.empty:
                if "status" in df_source.columns:
                    pend_rows = df_source[df_source["status"] == "PENDING"]
                else:
                    return 0
            else:
                # DB 직접 조회 (Supabase 우선, 없으면 SQLite)
                if self.use_supabase and self.supabase:
                    res = self.supabase.table("worktime_work_logs").select("*").eq("status", "PENDING").execute()
                    pend_rows = pd.DataFrame(res.data or [])
                else:
                    conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
                    pend_rows = pd.read_sql_query("SELECT * FROM work_logs WHERE status='PENDING'", conn)
                    conn.close()

            if pend_rows.empty:
                return 0

            now = datetime.now()
            resolved_records: List[WorkLogRecord] = []

            for _, r in pend_rows.iterrows():
                st = r.get("start_time")
                if pd.isna(st) or not st:
                    continue
                if isinstance(st, str):
                    try:
                        st = datetime.fromisoformat(st.replace("Z", ""))
                    except Exception:
                        continue
                elif hasattr(st, "to_pydatetime"):
                    st = st.to_pydatetime()
                if hasattr(st, "tzinfo") and st.tzinfo:
                    st = st.replace(tzinfo=None)

                raw_msg = str(r.get("raw_start_message", "") or "")
                est_mins = int(r.get("estimated_minutes", 0) or 0)

                threshold_hours = get_pending_timeout_hours(raw_msg, est_mins)
                elapsed_hours = (now - st).total_seconds() / 3600.0

                if elapsed_hours >= threshold_hours:
                    auto_actual = est_mins if est_mins > 0 else 60
                    auto_end_time = st + timedelta(minutes=auto_actual)
                    is_night = check_is_night_work(st, auto_end_time, raw_msg, est_mins, auto_actual)
                    is_weekend = check_is_weekend_work(st, auto_end_time, raw_msg, est_mins, auto_actual)

                    resolved_record = WorkLogRecord(
                        msg_hash=str(r.get("msg_hash", "")),
                        log_type=str(r.get("log_type", "작업")),
                        worker_name=str(r.get("worker_name", "")),
                        worker_title=str(r.get("worker_title", "")),
                        worker_team=str(r.get("worker_team", "")),
                        client_name=str(r.get("client_name", "")),
                        task_description=str(r.get("task_description", "")),
                        estimated_minutes=est_mins,
                        actual_minutes=auto_actual,
                        start_time=st,
                        end_time=auto_end_time,
                        status="COMPLETED",
                        is_night_work=is_night,
                        is_weekend_work=is_weekend,
                        raw_start_message=raw_msg,
                        raw_end_message=f"[자동완료] {int(threshold_hours)}시간 경과로 시작보고 기준 완료 처리"
                    )
                    resolved_records.append(resolved_record)

            if resolved_records:
                print(f"[DB] [자동완료 배치] {len(resolved_records)}건의 48시간 만료 미완료 작업을 COMPLETED로 승격 저장합니다.")
                self.save_work_logs(resolved_records)
                return resolved_records

            return []
        except Exception as e:
            print(f"[DB 오류] 자동완료 배치 예외: {e}")
            return []

    def resolve_stale_pending_tasks(self, msg_hashes: List[str], custom_minutes_map: Optional[Dict[str, int]] = None) -> int:
        """
        24시간 이상 방치된 미완료(PENDING) 작업들을 관리자가 수동 또는 예정시간 기준으로 즉시 완료(COMPLETED) 마감
        """
        if not msg_hashes:
            return 0

        updated_count = 0
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M")
        minutes_map = custom_minutes_map or {}

        # 1. 대상 레코드 정보 조회 (예정시간 등 파악)
        if self.use_supabase and self.supabase:
            try:
                res = self.supabase.table("worktime_work_logs").select("*").in_("msg_hash", msg_hashes).execute()
                records = res.data or []
                for r in records:
                    m_hash = r.get("msg_hash")
                    custom_mins = minutes_map.get(m_hash)
                    est_m = int(r.get("estimated_minutes") or 0)
                    act_m = custom_mins if (custom_mins is not None and custom_mins > 0) else (est_m if est_m > 0 else 60)
                    
                    st_str = r.get("start_time")
                    try:
                        st_dt = pd.to_datetime(st_str).to_pydatetime()
                        end_dt = st_dt + timedelta(minutes=act_m)
                        end_str = end_dt.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        end_str = now_str
                        st_dt = now
                        end_dt = now

                    is_night = check_is_night_work(st_dt, end_dt, r.get("raw_start_message", ""), est_m, act_m)
                    is_weekend = check_is_weekend_work(st_dt, end_dt, r.get("raw_start_message", ""), est_m, act_m)

                    up_payload = {
                        "status": "COMPLETED",
                        "actual_minutes": act_m,
                        "end_time": end_str,
                        "is_night_work": is_night,
                        "is_weekend_work": is_weekend,
                        "raw_end_message": f"[관리자 수동 마감] {round(act_m / 60.0, 1)}시간 완료 처리 ({now_str})"
                    }
                    self.supabase.table("worktime_work_logs").update(up_payload).eq("msg_hash", m_hash).execute()
                    updated_count += 1
            except Exception as e:
                print(f"[DB 오류] Supabase 미마감 작업 정리 실패: {e}")

        # 2. 로컬 SQLite 동기화
        for db_file in [config.LOCAL_DB_PATH, "kakao_work.db", "data/kakao_work.db"]:
            if Path(str(db_file)).exists():
                try:
                    conn = sqlite3.connect(str(db_file))
                    c = conn.cursor()
                    for m_hash in msg_hashes:
                        c.execute("SELECT estimated_minutes, start_time FROM work_logs WHERE msg_hash=?", (m_hash,))
                        row = c.fetchone()
                        if row:
                            custom_mins = minutes_map.get(m_hash)
                            est_m = int(row[0] or 0)
                            act_m = custom_mins if (custom_mins is not None and custom_mins > 0) else (est_m if est_m > 0 else 60)
                            c.execute("""
                                UPDATE work_logs 
                                SET status='COMPLETED', actual_minutes=?, end_time=?, raw_end_message=?
                                WHERE msg_hash=?
                            """, (act_m, now_str, f"[관리자 수동 마감] {now_str}", m_hash))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"[DB 오류] SQLite 미마감 작업 정리 실패: {e}")

        return updated_count

    def fetch_all_work_logs(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """
        Supabase 클라우드 DB에서 데이터를 최우선 조회 (오프라인 시 로컬 SQLite 조회)
        - start_date, end_date 지정 시 기간 범위 최적화 쿼리 적용
        - 48시간 경과한 PENDING 작업은 자동으로 COMPLETED 승격 처리
        """
        df = None
        if self.use_supabase and self.supabase:
            try:
                # Supabase 페이지네이션을 통해 10,000건 이상도 전수 조회
                all_data = []
                page_size = 1000
                start = 0
                while True:
                    query = self.supabase.table("worktime_work_logs")\
                        .select("*")\
                        .order("start_time", desc=True)
                    if start_date:
                        query = query.gte("start_time", f"{start_date} 00:00:00")
                    if end_date:
                        query = query.lte("start_time", f"{end_date} 23:59:59")
                    res = query.range(start, start + page_size - 1).execute()
                    rows = res.data or []
                    all_data.extend(rows)
                    if len(rows) < page_size:
                        break
                    start += page_size
                    
                df = pd.DataFrame(all_data)

                # 💾 로컬 SQLite 오프라인 백업 DB에도 최신 데이터 자동 동기화 (전체 조회 시에만)
                if not df.empty and not start_date and not end_date:
                    self._sync_to_local_sqlite(df)
            except Exception as e:
                print(f"[DB 오류] Supabase 조회 실패, 로컬 SQLite로 대체: {e}")

        # 로컬 SQLite Fallback
        if df is None:
            try:
                conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
                sql = "SELECT * FROM work_logs WHERE 1=1"
                params = []
                if start_date:
                    sql += " AND start_time >= ?"
                    params.append(f"{start_date} 00:00:00")
                if end_date:
                    sql += " AND start_time <= ?"
                    params.append(f"{end_date} 23:59:59")
                sql += " ORDER BY start_time DESC"
                df = pd.read_sql_query(sql, conn, params=params)
                conn.close()
            except Exception as e:
                print(f"[DB 오류] SQLite 데이터 조회 실패: {e}")
                return self._process_dataframe(pd.DataFrame())

        # 48시간 이상 경과한 잔여 PENDING 작업 검사 및 자동 완료 승격
        if not df.empty and "status" in df.columns and (df["status"] == "PENDING").any():
            try:
                resolved_records = self.resolve_expired_pending_tasks(df)
                if resolved_records:
                    for rec in resolved_records:
                        mask = df["msg_hash"] == rec.msg_hash
                        if mask.any():
                            df.loc[mask, "status"] = "COMPLETED"
                            df.loc[mask, "actual_minutes"] = rec.actual_minutes
                            ed_str = rec.end_time.strftime("%Y-%m-%d %H:%M") if rec.end_time else None
                            df.loc[mask, "end_time"] = ed_str
                            df.loc[mask, "raw_end_message"] = rec.raw_end_message
                            df.loc[mask, "is_night_work"] = rec.is_night_work
                            df.loc[mask, "is_weekend_work"] = rec.is_weekend_work
            except Exception as e:
                print(f"[DB 오류] PENDING 자동승격 반영 오류: {e}")

        return self._process_dataframe(df)

    def _sync_to_local_sqlite(self, df: pd.DataFrame):
        """Supabase에서 조회한 최신 데이터를 로컬 SQLite에 고속 일괄 동기화 (executemany 최적화)"""
        if df.empty:
            return
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            
            batch_data = []
            for _, r in df.iterrows():
                msg_hash = r.get("msg_hash", "")
                if not msg_hash:
                    continue
                st_val = str(r.get("start_time", ""))[:16]
                ed_raw = r.get("end_time")
                ed_val = str(ed_raw)[:16] if pd.notna(ed_raw) and ed_raw else ""
                batch_data.append((
                    str(msg_hash), str(r.get("log_type", "작업")), str(r.get("worker_name", "")),
                    str(r.get("worker_title", "")), str(r.get("worker_team", "")),
                    str(r.get("client_name", "")), str(r.get("task_description", "")),
                    int(r.get("estimated_minutes", 0) or 0), int(r.get("actual_minutes", 0) or 0),
                    st_val, ed_val,
                    str(r.get("status", "COMPLETED")),
                    1 if r.get("is_night_work") else 0,
                    1 if r.get("is_weekend_work") else 0,
                    str(r.get("raw_start_message", "") or ""),
                    str(r.get("raw_end_message", "") or "")
                ))
                
            if batch_data:
                cursor.executemany("""
                    INSERT INTO work_logs (
                        msg_hash, log_type, worker_name, worker_title, worker_team,
                        client_name, task_description, estimated_minutes, actual_minutes,
                        start_time, end_time, status, is_night_work, is_weekend_work,
                        raw_start_message, raw_end_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(msg_hash) DO UPDATE SET
                        actual_minutes=excluded.actual_minutes,
                        end_time=excluded.end_time,
                        status=excluded.status,
                        is_night_work=excluded.is_night_work,
                        raw_end_message=excluded.raw_end_message
                """, batch_data)
                conn.commit()
            conn.close()
        except Exception:
            pass

    def _process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=[
                "id", "msg_hash", "log_type", "worker_name", "worker_title", "worker_team",
                "client_name", "task_description", "estimated_minutes", "actual_minutes",
                "start_time", "end_time", "status", "is_night_work", "is_weekend_work",
                "actual_hours", "estimated_hours", "month_str", "date_str", "week_str", "week_label"
            ])
        
        # T와 공백이 혼재되어도 NaT로 증발하지 않도록 공백으로 정규화 후 안전 파싱
        df["start_time"] = pd.to_datetime(df["start_time"].astype(str).str.replace("T", " "), errors="coerce")
        if "end_time" in df.columns:
            df["end_time"] = pd.to_datetime(df["end_time"].astype(str).str.replace("T", " "), errors="coerce")
            
        df["actual_minutes"] = pd.to_numeric(df.get("actual_minutes", 0), errors="coerce").fillna(0).astype(int)
        df["estimated_minutes"] = pd.to_numeric(df.get("estimated_minutes", 0), errors="coerce").fillna(0).astype(int)
        
        if "status" not in df.columns:
            df["status"] = "COMPLETED"
        else:
            df["status"] = df["status"].fillna("COMPLETED").astype(str)
        
        df["actual_hours"] = (df["actual_minutes"] / 60.0).round(1)
        df["estimated_hours"] = (df["estimated_minutes"] / 60.0).round(1)
        
        valid_dates = df["start_time"].dropna()
        if not valid_dates.empty:
            df["month_str"] = df["start_time"].dt.strftime("%Y-%m")
            df["date_str"] = df["start_time"].dt.strftime("%Y-%m-%d")
            
            # 주차 레이블 생성 (월 경계를 넘지 않는 1일~말일 주차 분할)
            import calendar
            from datetime import date as d_date, timedelta as d_timedelta
            def get_week_label(dt):
                if pd.isna(dt):
                    return "미정"
                if hasattr(dt, "to_pydatetime"):
                    dt = dt.to_pydatetime()
                y, m, d = dt.year, dt.month, dt.day
                target_date = d_date(y, m, d)
                last_day_num = calendar.monthrange(y, m)[1]
                cur_start = d_date(y, m, 1)
                week_num = 1
                while cur_start.day <= last_day_num:
                    days_to_sun = 6 - cur_start.weekday()
                    cur_sun = cur_start + d_timedelta(days=days_to_sun)
                    cur_end = min(cur_sun, d_date(y, m, last_day_num))
                    if cur_start <= target_date <= cur_end:
                        return f"{y:04d}-{m:02d} {week_num}주차 ({cur_start.strftime('%m/%d')}~{cur_end.strftime('%m/%d')})"
                    cur_start = cur_end + d_timedelta(days=1)
                    week_num += 1
                    if cur_start.month != m:
                        break
                return f"{y:04d}-{m:02d} 1주차"
                
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

    def save_outlook_schedules(self, records: List[OutlookScheduleRecord]) -> int:
        """
        아웃룩 일정 레코드들을 Supabase(클라우드) 및 로컬 SQLite에 Upsert 저장
        """
        if not records:
            return 0

        # 1. Supabase Cloud DB Upsert
        if self.use_supabase and self.supabase:
            try:
                rows = [r.to_dict() for r in records]
                self.supabase.table("worktime_outlook_schedules").upsert(rows, on_conflict="entry_id").execute()
                print(f"[DB] [Cloud] Supabase worktime_outlook_schedules에 {len(records)}건 Upsert 완료")
            except Exception as e:
                print(f"[DB 오류] Supabase 아웃룩 스케줄 저장 실패: {e}")

        # 2. 로컬 SQLite 백업 저장
        saved_count = 0
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            for r in records:
                cursor.execute("""
                    INSERT INTO outlook_schedules (
                        entry_id, worker_name, worker_team, subject, schedule_type,
                        start_time, end_time, duration_hours, is_all_day, is_leave,
                        leave_type, location, body, color_tag, created_by, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(entry_id) DO UPDATE SET
                        worker_name=excluded.worker_name,
                        worker_team=excluded.worker_team,
                        subject=excluded.subject,
                        schedule_type=excluded.schedule_type,
                        start_time=excluded.start_time,
                        end_time=excluded.end_time,
                        duration_hours=excluded.duration_hours,
                        is_all_day=excluded.is_all_day,
                        is_leave=excluded.is_leave,
                        leave_type=excluded.leave_type,
                        location=excluded.location,
                        body=excluded.body,
                        color_tag=excluded.color_tag,
                        created_by=excluded.created_by,
                        synced_at=excluded.synced_at
                """, (
                    r.entry_id, r.worker_name, r.worker_team, r.subject, r.schedule_type,
                    r.start_time, r.end_time, r.duration_hours,
                    1 if r.is_all_day else 0, 1 if r.is_leave else 0,
                    r.leave_type, r.location, r.body, r.color_tag, r.created_by, r.synced_at
                ))
            conn.commit()
            conn.close()
            saved_count = len(records)
        except Exception as e:
            print(f"[DB 오류] 로컬 SQLite 아웃룩 스케줄 저장 실패: {e}")

        return saved_count

    def fetch_outlook_schedules(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """
        아웃룩 일정 데이터프레임 조회 (Supabase 우선, Fallback 로컬 SQLite)
        """
        df = pd.DataFrame()
        if self.use_supabase and self.supabase:
            try:
                query = self.supabase.table("worktime_outlook_schedules").select("*")
                if start_date:
                    query = query.gte("start_time", f"{start_date} 00:00:00")
                if end_date:
                    query = query.lte("end_time", f"{end_date} 23:59:59")
                res = query.order("start_time").execute()
                if res.data:
                    df = pd.DataFrame(res.data)
            except Exception as e:
                # 테이블이 아직 Supabase에 없을 경우 등 조용히 로컬 SQLite fallback
                df = pd.DataFrame()

        if df.empty:
            try:
                conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
                sql = "SELECT * FROM outlook_schedules WHERE 1=1"
                params = []
                if start_date:
                    sql += " AND start_time >= ?"
                    params.append(f"{start_date} 00:00:00")
                if end_date:
                    sql += " AND end_time <= ?"
                    params.append(f"{end_date} 23:59:59")
                sql += " ORDER BY start_time ASC"
                df = pd.read_sql_query(sql, conn, params=params)
                conn.close()
            except Exception as e:
                print(f"[DB 오류] 로컬 SQLite 아웃룩 스케줄 조회 실패: {e}")
                df = pd.DataFrame()

        if not df.empty:
            if "start_time" in df.columns:
                df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
            if "end_time" in df.columns:
                df["end_time"] = pd.to_datetime(df["end_time"], errors="coerce")
            if "is_all_day" in df.columns:
                df["is_all_day"] = df["is_all_day"].astype(bool)
            if "is_leave" in df.columns:
                df["is_leave"] = df["is_leave"].astype(bool)

            # 🛡️ 다일 분할 일정(일일 9.0h)과 중복되는 과거 미분할 통짜 다일 일정(81.0h 등) 원천 차단
            if "start_time" in df.columns and "end_time" in df.columns and "duration_hours" in df.columns:
                df["duration_hours"] = pd.to_numeric(df["duration_hours"], errors="coerce").fillna(0.0)
                bad_mask = (df["start_time"].dt.date != df["end_time"].dt.date) & (df["duration_hours"] > 9.0)
                if bad_mask.any():
                    df = df[~bad_mask].reset_index(drop=True)
            if "duration_hours" in df.columns:
                df["duration_hours"] = pd.to_numeric(df["duration_hours"], errors="coerce").fillna(0.0)

        return df


db_manager = DatabaseManager()

def fetch_outlook_schedules(start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
    """모듈 레벨 안전 헬퍼"""
    return db_manager.fetch_outlook_schedules(start_date, end_date)

def save_outlook_schedules(records: List[OutlookScheduleRecord]) -> int:
    """모듈 레벨 안전 헬퍼"""
    return db_manager.save_outlook_schedules(records)
