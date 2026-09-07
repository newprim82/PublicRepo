import sqlite3
from typing import List, Dict, Optional, Any
from datetime import datetime

from ..config import config
from ..database.supabase_client import db_manager
from ..dashboard.common.ui_helpers import get_current_kst_time


class EmailDispatchService:
    """
    업무 실적 Summary 메일 발송 이력 관리 서비스
    - 수동 즉시 발송(MANUAL_IMMEDIATE), 주간 자동 발송(AUTO_WEEKLY), 월간 자동 발송(AUTO_MONTHLY) 전수 DB 기록
    - 로컬 SQLite (email_dispatch_logs) + Supabase 클라우드 (worktime_email_dispatch_logs) 하이브리드 지원
    """

    _table_initialized: bool = False

    @classmethod
    def init_table(cls):
        """로컬 SQLite 발송 로그 테이블 생성 및 인덱스 초기화 (1회만 실행 가드)"""
        if cls._table_initialized:
            return
        db_path = config.LOCAL_DB_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_dispatch_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dispatch_type TEXT NOT NULL,
                recipient_emails TEXT NOT NULL,
                sender_email TEXT NOT NULL,
                selected_team TEXT DEFAULT '',
                period_label TEXT DEFAULT '',
                subject TEXT DEFAULT '',
                status TEXT NOT NULL,
                error_message TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_email_dispatch_created_id
            ON email_dispatch_logs(created_at DESC, id DESC)
        """)
        conn.commit()
        conn.close()
        cls._table_initialized = True

    @classmethod
    def record_dispatch(
        cls,
        dispatch_type: str,
        recipient_emails: str,
        sender_email: str,
        selected_team: str = '',
        period_label: str = '',
        subject: str = '',
        status: str = 'SUCCESS',
        error_message: str = ''
    ) -> bool:
        """
        메일 발송 결과 DB 저장 (로컬 SQLite 저장 + Supabase 클라우드 동기화)
        시간은 항상 KST 한국시간 기준 초 단위(YYYY-MM-DD HH:MM:SS)로만 저장 (+00 타임존 오프셋 없음)
        """
        cls.init_table()
        # 🌐 무조건 time.bora.net (LGU+ 타임서버) NTP 기준 한국 표준시(KST, UTC+9) 적용
        try:
            from ..dashboard.common.ui_helpers import get_current_kst_time
            now_kst = get_current_kst_time()
        except Exception:
            import socket, struct, time as _time
            from datetime import timezone, timedelta
            now_ts = _time.time()
            try:
                client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                client.settimeout(0.6)
                client.sendto(b'\x1b' + 47 * b'\0', ('time.bora.net', 123))
                resp, _ = client.recvfrom(1024)
                if resp:
                    now_ts = float(struct.unpack('!12I', resp)[10] - 2208988800)
            except Exception:
                pass
            now_kst = datetime.fromtimestamp(now_ts, tz=timezone(timedelta(hours=9)))

        now_str = now_kst.strftime('%Y-%m-%d %H:%M:%S')

        # 1. 로컬 SQLite에 무조건 최우선 저장
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO email_dispatch_logs (
                    dispatch_type, recipient_emails, sender_email,
                    selected_team, period_label, subject, status, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dispatch_type, recipient_emails, sender_email,
                selected_team, period_label, subject, status, error_message, now_str
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f'[이메일 로그 오류] SQLite 저장 실패: {e}')

        # 2. Supabase 클라우드 동기화 시도 (테이블 미존재 시 무시)
        if db_manager.use_supabase and db_manager.supabase:
            try:
                db_manager.supabase.table('worktime_email_dispatch_logs').insert({
                    'dispatch_type': dispatch_type,
                    'recipient_emails': recipient_emails,
                    'sender_email': sender_email,
                    'selected_team': selected_team,
                    'period_label': period_label,
                    'subject': subject,
                    'status': status,
                    'error_message': error_message,
                    'created_at': now_str
                }).execute()
            except Exception:
                pass

        return True

    @classmethod
    def get_recent_dispatches(cls, limit: int = 5) -> List[Dict[str, Any]]:
        """
        최근 발송 이력 N건 최신순 조회
        """
        cls.init_table()
        dispatches = []

        # 1. Supabase 클라우드 조회 시도
        if db_manager.use_supabase and db_manager.supabase:
            try:
                res = db_manager.supabase.table('worktime_email_dispatch_logs')\
                    .select('*')\
                    .order('created_at', desc=True)\
                    .limit(limit)\
                    .execute()
                if res.data:
                    return res.data
            except Exception:
                pass

        # 2. 로컬 SQLite Fallback
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, dispatch_type, recipient_emails, sender_email,
                       selected_team, period_label, subject, status, error_message, created_at
                FROM email_dispatch_logs
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            for r in rows:
                dispatches.append(dict(r))
            conn.close()
        except Exception as e:
            print(f'[이메일 로그 오류] SQLite 조회 실패: {e}')

        return dispatches
