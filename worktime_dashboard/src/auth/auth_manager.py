"""
시스템 관리자 인증 및 계정 권한(Super Admin / Admin) 관리 매니저
- newprim: Super Admin (모든 메뉴 및 시스템 관리, 계정 등록 권한 보유)
- 그 외 계정: Admin (일반 관리 권한, 시스템 관리 메뉴 접근 불가)
- 3중 영구 저장: 로컬 SQLite + 로컬 JSON + Supabase Cloud DB (전용 테이블 & 전역 슬롯 -99995/-99994 2중화)
"""

import os
import json
import time
import sqlite3
import secrets
import hashlib
import hmac
import threading
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import streamlit as st
import streamlit.components.v1 as components

# 세션 유지 시간: 기본 7일 (환경변수 AUTH_SESSION_DAYS로 조정 가능)
try:
    SESSION_DAYS = max(1, int(os.getenv("AUTH_SESSION_DAYS", "7") or "7"))
except ValueError:
    SESSION_DAYS = 7
SESSION_DURATION_SECONDS = SESSION_DAYS * 24 * 3600

# 브라우저 세션 쿠키 이름 및 Supabase 클라우드 영구 슬롯 번호
COOKIE_NAME = "worklens_session"
CLOUD_ACCOUNTS_RATE_SLOT = -99995
CLOUD_ACCOUNTS_PREFIX = "__ADMIN_ACCOUNTS__:"
CLOUD_SESSIONS_RATE_SLOT = -99994
CLOUD_SESSION_PREFIX = "__AUTH_SESSION__:"

SENTINEL_TS = "2000-01-01 00:00:00"
AUTO_UPWARD_SYNC_MIN_TS_WINDOWS = "2026-10-28 00:00:00"
ACCOUNTS_CACHE_TTL_SECONDS = 60.0
NEGATIVE_TOKEN_CACHE_TTL_SECONDS = 30.0
TOMBSTONE_RETENTION_DAYS = 90

# 프로젝트 루트 및 파일 경로
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SESSION_CACHE_FILE = DATA_DIR / ".session_cache.json"
LOCAL_ACCOUNTS_FILE = DATA_DIR / "admin_accounts.json"

SUPER_ADMIN_USERNAME = "newprim"
_FILE_LOCK = threading.RLock()


def _get_initial_super_admin_pwd() -> str:
    """초기 최고 관리자 비밀번호 조회 (환경변수 -> st.secrets -> 기본값)"""
    env_pwd = os.getenv("SUPER_ADMIN_INITIAL_PWD", "").strip()
    if env_pwd:
        return env_pwd
    try:
        secret_pwd = str(st.secrets.get("SUPER_ADMIN_INITIAL_PWD", "") or "").strip()
        if secret_pwd:
            return secret_pwd
    except Exception:
        pass
    return "admin1234!"


DEFAULT_SUPER_ADMIN_PWD = _get_initial_super_admin_pwd()

# =========================================================
# 🔒 단방향 솔트 해시 (PBKDF2-HMAC-SHA256) 보안 유틸리티
# - 복호화 키 자체가 세상에 아예 존재하지 않는 단방향 해시
# - 계정마다 무작위 16바이트 솔트(Salt)를 부여하여 100,000회 반복 해시
# =========================================================
PBKDF2_ALGO = "sha256"
PBKDF2_ITERATIONS = 100_000
SALT_BYTES = 16


def hash_password(raw_password: str) -> str:
    """
    단방향 솔트 해시 생성 (PBKDF2-HMAC-SHA256)
    포맷: pbkdf2:sha256:100000${salt_hex}${hash_hex}
    """
    salt = secrets.token_hex(SALT_BYTES)
    hash_bytes = hashlib.pbkdf2_hmac(
        PBKDF2_ALGO,
        raw_password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS
    )
    return f"pbkdf2:{PBKDF2_ALGO}:{PBKDF2_ITERATIONS}${salt}${hash_bytes.hex()}"


def is_hashed_password(val: str) -> bool:
    """해당 문자열이 이미 PBKDF2 단방향 해시 포맷인지 확인"""
    if not val or not isinstance(val, str):
        return False
    return val.startswith("pbkdf2:") and "$" in val


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """
    사용자가 입력한 평문 비밀번호와 DB에 저장된 해시값을 단방향 대조 검증
    - 타이밍 공격(Timing Attack) 방지: hmac.compare_digest
    - 이전 평문 데이터에 대한 하위 호환성 지원
    """
    if not stored_hash or not plain_password:
        return False

    # 1. 이전 평문 데이터 하위 호환성
    if not is_hashed_password(stored_hash):
        return hmac.compare_digest(plain_password.strip(), stored_hash.strip())

    # 2. PBKDF2 단방향 솔트 해시 대조
    try:
        parts = stored_hash.split("$")
        if len(parts) != 3:
            return False
        meta, salt, expected_hash = parts
        _, algo, iter_str = meta.split(":")
        iterations = int(iter_str)

        computed_bytes = hashlib.pbkdf2_hmac(
            algo,
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations
        )
        return hmac.compare_digest(computed_bytes.hex(), expected_hash)
    except Exception:
        return False


def _normalize_ts(val: Any, fallback: str = SENTINEL_TS) -> str:
    """타임스탬프 문자열을 'YYYY-MM-DD HH:MM:SS' 19자리 표준 포맷으로 정규화"""
    if not val:
        return fallback
    s = str(val).strip().replace("T", " ")
    if len(s) >= 19 and s[4:5] == "-" and s[7:8] == "-" and s[10:11] == " ":
        return s[:19]
    if len(s) == 10 and s[4:5] == "-" and s[7:8] == "-":
        return f"{s} 00:00:00"
    return fallback


def _password_fingerprint(stored_password: str) -> str:
    """세션 무효화 대조용 비밀번호 해시 지문 (원문 노출 없는 16자리 SHA-256 요약)"""
    return hashlib.sha256(str(stored_password or "").encode("utf-8")).hexdigest()[:16]


def _atomic_write_json(target_path: Path, payload: Any):
    """멀티스레드 파일 손상 방지를 위한 원자적 JSON 저장"""
    with _FILE_LOCK:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(target_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_name, str(target_path))
        except Exception:
            try:
                if os.path.exists(tmp_name):
                    os.remove(tmp_name)
            except Exception:
                pass


DEFAULT_ACCOUNTS = {
    "newprim": {
        "username": "newprim",
        "password": hash_password(DEFAULT_SUPER_ADMIN_PWD),
        "name": "최고 관리자",
        "role": "SUPER_ADMIN",
        "note": "시스템 최고 관리자 (전체 권한)",
        "created_at": SENTINEL_TS,
        "updated_at": SENTINEL_TS
    }
}


class AuthManager:
    _cached_accounts: Optional[Dict[str, Dict[str, Any]]] = None
    _cached_deleted: Dict[str, str] = {}
    _accounts_loaded_at: float = 0.0
    _negative_token_cache: Dict[str, float] = {}
    _last_session_gc_at: float = 0.0

    # 🔒 무차별 대입 공격(Brute Force) 방어 설정 (5회 실패 시 3분 잠금)
    _failed_attempts: Dict[str, Dict[str, Any]] = {}
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION_SECONDS = 180

    @staticmethod
    def _is_cloud_sync_disabled() -> bool:
        return os.getenv("WORKLENS_DISABLE_CLOUD_AUTH_SYNC", "").strip() == "1"

    @staticmethod
    def _now_kst_str() -> str:
        try:
            from ..common.time_utils import get_current_kst_time
            return get_current_kst_time().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _normalize_account_record(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        un = str(raw.get("username", "") or "").strip()
        pwd = str(raw.get("password", "") or "").strip()
        if not un or not pwd:
            return None
        c_ts = _normalize_ts(raw.get("created_at"), SENTINEL_TS)
        u_ts = _normalize_ts(raw.get("updated_at"), c_ts)
        role = "SUPER_ADMIN" if un.lower() == SUPER_ADMIN_USERNAME.lower() else str(raw.get("role", "ADMIN") or "ADMIN")
        return {
            "username": un,
            "password": pwd,
            "name": str(raw.get("name", "") or ""),
            "role": role,
            "note": str(raw.get("note", "") or ""),
            "created_at": c_ts,
            "updated_at": u_ts
        }

    @classmethod
    def _can_auto_upward_sync_account(cls, acc: Dict[str, Any]) -> bool:
        """
        조회 시 로컬 계정을 클라우드로 자동 역동기화해도 안전한지 검증
        - SENTINEL_TS('2000-01-01 00:00:00') 자동 초기화 레코드는 절대 클라우드 덮어쓰기 금지
        - Windows 로컬 개발 PC에 남아 있던 과거(2026-10-28 이전) 테스트 계정이 프로덕션을 오염시키지 않도록 차단
        """
        u_ts = _normalize_ts(acc.get("updated_at") or acc.get("created_at"), SENTINEL_TS)
        if u_ts <= SENTINEL_TS:
            return False
        if os.name == "nt" and u_ts < AUTO_UPWARD_SYNC_MIN_TS_WINDOWS:
            return False
        return True

    # =========================================================
    # 1. 로컬 SQLite & JSON 저장소 초기화 및 동기화
    # =========================================================
    @classmethod
    def _get_db_path(cls) -> Path:
        try:
            from ..config import config
            return Path(config.LOCAL_DB_PATH)
        except Exception:
            return DATA_DIR / "worklog.db"

    @classmethod
    def _init_db(cls):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        db_path = cls._get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_accounts (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    name TEXT DEFAULT '',
                    role TEXT DEFAULT 'ADMIN',
                    note TEXT DEFAULT '',
                    created_at TEXT DEFAULT '2000-01-01 00:00:00',
                    updated_at TEXT DEFAULT '2000-01-01 00:00:00'
                )
            """)
            # 기본 newprim 계정 보장 (Sentinel 시각을 부여하여 클라우드/실제 변경본을 절대 덮어쓰지 않음)
            cur.execute("SELECT 1 FROM admin_accounts WHERE lower(username) = ?", (SUPER_ADMIN_USERNAME.lower(),))
            if not cur.fetchone():
                cur.execute("""
                    INSERT OR IGNORE INTO admin_accounts (username, password, name, role, note, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    SUPER_ADMIN_USERNAME,
                    DEFAULT_ACCOUNTS["newprim"]["password"],
                    "최고 관리자",
                    "SUPER_ADMIN",
                    "시스템 최고 관리자",
                    SENTINEL_TS,
                    SENTINEL_TS
                ))
            conn.commit()
            conn.close()
        except Exception:
            pass

    @classmethod
    def _get_db_conn(cls):
        return sqlite3.connect(str(cls._get_db_path()))

    @classmethod
    def _sync_accounts_to_local(cls, accounts_map: Dict[str, Dict[str, Any]], deleted_keys: Optional[List[str]] = None):
        """병합된 최신 계정 맵을 로컬 SQLite 및 로컬 JSON에 일관되게 반영"""
        cls._init_db()
        try:
            conn = cls._get_db_conn()
            cur = conn.cursor()
            if deleted_keys:
                for dk in deleted_keys:
                    if dk.lower() != SUPER_ADMIN_USERNAME.lower():
                        cur.execute("DELETE FROM admin_accounts WHERE lower(username) = ?", (dk.lower(),))
            for k, acc in accounts_map.items():
                cur.execute("DELETE FROM admin_accounts WHERE lower(username) = ? AND username != ?", (k.lower(), acc["username"]))
                cur.execute("""
                    INSERT OR REPLACE INTO admin_accounts (username, password, name, role, note, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    acc["username"],
                    acc["password"],
                    acc.get("name", ""),
                    "SUPER_ADMIN" if k.lower() == SUPER_ADMIN_USERNAME.lower() else acc.get("role", "ADMIN"),
                    acc.get("note", ""),
                    _normalize_ts(acc.get("created_at"), SENTINEL_TS),
                    _normalize_ts(acc.get("updated_at"), SENTINEL_TS)
                ))
            conn.commit()
            conn.close()
        except Exception:
            pass

        try:
            _atomic_write_json(LOCAL_ACCOUNTS_FILE, accounts_map)
        except Exception:
            pass

    # =========================================================
    # 1-B. Supabase Cloud 영구 저장소 연동 (-99995 계정 / -99994 세션)
    # =========================================================
    @classmethod
    def _get_supabase_client(cls):
        if cls._is_cloud_sync_disabled():
            return None
        try:
            from ..database.supabase_client import db_manager
            if getattr(db_manager, "use_supabase", False) and getattr(db_manager, "supabase", None):
                return db_manager.supabase
        except Exception:
            pass
        return None

    @classmethod
    def _load_accounts_from_cloud(cls) -> Tuple[str, Dict[str, Dict[str, Any]], Dict[str, str]]:
        """
        Supabase 클라우드에서 관리자 계정 원장 로드
        반환: (status, accounts_map, deleted_map)
        status: 'OK' | 'EMPTY' | 'ERROR' | 'DISABLED'
        """
        if cls._is_cloud_sync_disabled():
            return "DISABLED", {}, {}

        client = cls._get_supabase_client()
        if not client:
            return "DISABLED", {}, {}

        cloud_accounts: Dict[str, Dict[str, Any]] = {}
        deleted_map: Dict[str, str] = {}
        slot_query_ok = False
        dedicated_query_ok = False

        # 1. worktime_hourly_rates 전역 영구 슬롯 (-99995) 조회
        try:
            res = client.table("worktime_hourly_rates").select("job_title, updated_at").eq("hourly_rate", CLOUD_ACCOUNTS_RATE_SLOT).execute()
            slot_query_ok = True
            if res.data:
                best_synced_at = ""
                for row in res.data:
                    jt = str(row.get("job_title", "") or "")
                    if not jt.startswith(CLOUD_ACCOUNTS_PREFIX):
                        continue
                    raw_json = jt[len(CLOUD_ACCOUNTS_PREFIX):]
                    parsed = json.loads(raw_json)
                    if not isinstance(parsed, dict):
                        continue

                    if "_schema_v" in parsed and isinstance(parsed.get("accounts"), dict):
                        row_synced = _normalize_ts(parsed.get("synced_at") or row.get("updated_at"), SENTINEL_TS)
                        raw_accs = parsed.get("accounts", {})
                        raw_del = parsed.get("deleted", {})
                        if isinstance(raw_del, dict):
                            for du, dts in raw_del.items():
                                dk = str(du).strip().lower()
                                if dk and dk != SUPER_ADMIN_USERNAME.lower():
                                    norm_dts = _normalize_ts(dts, row_synced)
                                    if norm_dts > deleted_map.get(dk, ""):
                                        deleted_map[dk] = norm_dts
                        if row_synced >= best_synced_at:
                            best_synced_at = row_synced
                        for _, acc_val in raw_accs.items():
                            norm_acc = cls._normalize_account_record(acc_val)
                            if norm_acc:
                                uk = norm_acc["username"].lower()
                                existing = cloud_accounts.get(uk)
                                if not existing or norm_acc["updated_at"] >= existing["updated_at"]:
                                    cloud_accounts[uk] = norm_acc
                    else:
                        for _, acc_val in parsed.items():
                            norm_acc = cls._normalize_account_record(acc_val)
                            if norm_acc:
                                uk = norm_acc["username"].lower()
                                existing = cloud_accounts.get(uk)
                                if not existing or norm_acc["updated_at"] >= existing["updated_at"]:
                                    cloud_accounts[uk] = norm_acc
        except Exception:
            slot_query_ok = False

        # 2. 전용 테이블(worktime_admin_accounts) 존재 시 보조 병합
        try:
            res_ded = client.table("worktime_admin_accounts").select("*").execute()
            dedicated_query_ok = True
            if res_ded.data:
                for row in res_ded.data:
                    norm_acc = cls._normalize_account_record(row)
                    if not norm_acc:
                        continue
                    uk = norm_acc["username"].lower()
                    if uk in deleted_map and norm_acc["updated_at"] <= deleted_map[uk]:
                        continue
                    existing = cloud_accounts.get(uk)
                    if not existing or norm_acc["updated_at"] > existing["updated_at"]:
                        cloud_accounts[uk] = norm_acc
        except Exception:
            pass

        # 삭제 tombstone 필터 적용
        for dk, dts in list(deleted_map.items()):
            if dk in cloud_accounts and dk != SUPER_ADMIN_USERNAME.lower():
                if cloud_accounts[dk]["updated_at"] <= dts:
                    del cloud_accounts[dk]

        if cloud_accounts:
            return "OK", cloud_accounts, deleted_map
        if slot_query_ok or dedicated_query_ok:
            return "EMPTY", {}, deleted_map
        return "ERROR", {}, {}

    @classmethod
    def _save_accounts_to_cloud(
        cls,
        accounts_map: Dict[str, Dict[str, Any]],
        deleted_map: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        관리자 계정 원장을 Supabase 클라우드에 무중단 영구 저장
        - Insert-New-Then-Delete-Old 패턴으로 빈 조회 구간(Empty Window) 원천 제거
        """
        client = cls._get_supabase_client()
        if not client:
            return False

        now_str = cls._now_kst_str()
        cutoff_str = (datetime.now() - timedelta(days=TOMBSTONE_RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

        merged_deleted: Dict[str, str] = {}
        source_del = deleted_map if deleted_map is not None else cls._cached_deleted
        for dk, dts in (source_del or {}).items():
            k_low = str(dk).strip().lower()
            norm_dts = _normalize_ts(dts, now_str)
            if k_low and k_low != SUPER_ADMIN_USERNAME.lower() and norm_dts >= cutoff_str:
                if k_low not in accounts_map:
                    merged_deleted[k_low] = norm_dts

        clean_accounts: Dict[str, Dict[str, Any]] = {}
        for k, acc in accounts_map.items():
            norm_acc = cls._normalize_account_record(acc)
            if not norm_acc:
                continue
            if not is_hashed_password(norm_acc["password"]):
                norm_acc["password"] = hash_password(norm_acc["password"])
            clean_accounts[norm_acc["username"].lower()] = norm_acc

        payload_obj = {
            "_schema_v": 2,
            "synced_at": now_str,
            "accounts": clean_accounts,
            "deleted": merged_deleted
        }
        new_job_title = f"{CLOUD_ACCOUNTS_PREFIX}{json.dumps(payload_obj, ensure_ascii=False, sort_keys=True)}"

        saved_ok = False
        # 1. worktime_hourly_rates (-99995) 무중단 교체 (신규 행 먼저 Upsert -> 이전 스냅샷만 Delete)
        try:
            client.table("worktime_hourly_rates").upsert(
                {"job_title": new_job_title, "hourly_rate": CLOUD_ACCOUNTS_RATE_SLOT},
                on_conflict="job_title"
            ).execute()
            client.table("worktime_hourly_rates").delete().eq(
                "hourly_rate", CLOUD_ACCOUNTS_RATE_SLOT
            ).neq("job_title", new_job_title).execute()
            saved_ok = True
        except Exception:
            pass

        # 2. 전용 테이블(worktime_admin_accounts) 존재 시 동기화
        try:
            rows = list(clean_accounts.values())
            if rows:
                client.table("worktime_admin_accounts").upsert(rows, on_conflict="username").execute()
            for dk in merged_deleted.keys():
                client.table("worktime_admin_accounts").delete().ilike("username", dk).execute()
            saved_ok = True
        except Exception:
            pass

        cls._cached_deleted = merged_deleted
        return saved_ok

    # =========================================================
    # 1-C. 로컬 + 클라우드 세션 캐시 (-99994 개별 행 저장으로 경합 제거)
    # =========================================================
    @staticmethod
    def _hash_token(token: str) -> str:
        """세션 토큰 원문 노출 방지를 위한 SHA-256 단방향 해시"""
        return hashlib.sha256(str(token).encode("utf-8")).hexdigest()

    @staticmethod
    def _load_session_cache() -> Dict[str, Any]:
        """로컬 파일 기반 세션 캐시 로드 (만료된 세션 자동 정리)"""
        with _FILE_LOCK:
            if SESSION_CACHE_FILE.exists():
                try:
                    with open(SESSION_CACHE_FILE, "r", encoding="utf-8") as f:
                        raw_cache = json.load(f)
                    if not isinstance(raw_cache, dict):
                        return {}
                    now = time.time()
                    valid_cache = {
                        k: v for k, v in raw_cache.items()
                        if isinstance(v, dict) and (now - float(v.get("login_at", 0) or 0) < SESSION_DURATION_SECONDS)
                    }
                    return valid_cache
                except Exception:
                    return {}
        return {}

    @staticmethod
    def _save_session_cache(cache: Dict[str, Any]):
        """로컬 파일 기반 세션 캐시 원자적 저장"""
        _atomic_write_json(SESSION_CACHE_FILE, cache)

    @classmethod
    def _save_session_to_cloud(cls, token_hash: str, session_info: Dict[str, Any]):
        """개별 세션 해시 레코드를 Supabase -99994 슬롯에 독립 저장 (타 사용자 세션과 무경합)"""
        client = cls._get_supabase_client()
        if not client or not token_hash:
            return
        safe_info = {
            "username": session_info.get("username", ""),
            "name": session_info.get("name", ""),
            "role": session_info.get("role", "ADMIN"),
            "login_at": float(session_info.get("login_at", time.time())),
            "token_hash": token_hash,
            "pwd_fp": session_info.get("pwd_fp", "")
        }
        prefix = f"{CLOUD_SESSION_PREFIX}{token_hash}:"
        new_jt = f"{prefix}{json.dumps(safe_info, ensure_ascii=False, sort_keys=True)}"
        try:
            client.table("worktime_hourly_rates").upsert(
                {"job_title": new_jt, "hourly_rate": CLOUD_SESSIONS_RATE_SLOT},
                on_conflict="job_title"
            ).execute()
            client.table("worktime_hourly_rates").delete().eq(
                "hourly_rate", CLOUD_SESSIONS_RATE_SLOT
            ).like("job_title", f"{prefix}%").neq("job_title", new_jt).execute()
        except Exception:
            pass

        cls._negative_token_cache.pop(token_hash, None)
        cls._gc_expired_cloud_sessions_if_needed()

    @classmethod
    def _get_session_from_cloud(cls, token_hash: str) -> Optional[Dict[str, Any]]:
        """브라우저 쿠키의 token_hash로 Supabase -99994 슬롯에서 세션 복원"""
        if not token_hash:
            return None
        now = time.time()
        neg_until = cls._negative_token_cache.get(token_hash, 0.0)
        if neg_until > now:
            return None

        client = cls._get_supabase_client()
        if not client:
            return None

        prefix = f"{CLOUD_SESSION_PREFIX}{token_hash}:"
        try:
            res = client.table("worktime_hourly_rates").select("job_title").eq(
                "hourly_rate", CLOUD_SESSIONS_RATE_SLOT
            ).like("job_title", f"{prefix}%").execute()
            if res.data:
                for row in res.data:
                    jt = str(row.get("job_title", "") or "")
                    if jt.startswith(prefix):
                        parsed = json.loads(jt[len(prefix):])
                        if isinstance(parsed, dict):
                            login_at = float(parsed.get("login_at", 0) or 0)
                            if now - login_at < SESSION_DURATION_SECONDS:
                                return parsed
                # 만료된 행 정리
                client.table("worktime_hourly_rates").delete().eq(
                    "hourly_rate", CLOUD_SESSIONS_RATE_SLOT
                ).like("job_title", f"{prefix}%").execute()
        except Exception:
            return None

        cls._negative_token_cache[token_hash] = now + NEGATIVE_TOKEN_CACHE_TTL_SECONDS
        return None

    @classmethod
    def _delete_session_from_cloud(cls, token_hash: str):
        """로그아웃 시 해당 token_hash 레코드만 핀포인트 삭제"""
        client = cls._get_supabase_client()
        if not client or not token_hash:
            return
        prefix = f"{CLOUD_SESSION_PREFIX}{token_hash}:"
        try:
            client.table("worktime_hourly_rates").delete().eq(
                "hourly_rate", CLOUD_SESSIONS_RATE_SLOT
            ).like("job_title", f"{prefix}%").execute()
        except Exception:
            pass

    @classmethod
    def _revoke_user_sessions(cls, username: str, keep_token_hash: Optional[str] = None):
        """계정 삭제 또는 비밀번호 변경 시 해당 사용자의 기존 활성 세션을 로컬·클라우드에서 일괄 무효화"""
        target_low = username.strip().lower()
        # 1. 로컬 세션 캐시 정리
        cache = cls._load_session_cache()
        changed = False
        for th, s_info in list(cache.items()):
            if th == keep_token_hash:
                continue
            if str(s_info.get("username", "")).strip().lower() == target_low:
                del cache[th]
                changed = True
        if changed:
            cls._save_session_cache(cache)

        # 2. 클라우드 세션 슬롯(-99994) 정리
        client = cls._get_supabase_client()
        if not client:
            return
        try:
            res = client.table("worktime_hourly_rates").select("job_title").eq(
                "hourly_rate", CLOUD_SESSIONS_RATE_SLOT
            ).execute()
            for row in (res.data or []):
                jt = str(row.get("job_title", "") or "")
                if not jt.startswith(CLOUD_SESSION_PREFIX):
                    continue
                rest = jt[len(CLOUD_SESSION_PREFIX):]
                sep_idx = rest.find(":")
                if sep_idx <= 0:
                    continue
                th = rest[:sep_idx]
                if keep_token_hash and th == keep_token_hash:
                    continue
                try:
                    info = json.loads(rest[sep_idx + 1:])
                    if str(info.get("username", "")).strip().lower() == target_low:
                        client.table("worktime_hourly_rates").delete().eq(
                            "hourly_rate", CLOUD_SESSIONS_RATE_SLOT
                        ).eq("job_title", jt).execute()
                except Exception:
                    pass
        except Exception:
            pass

    @classmethod
    def _gc_expired_cloud_sessions_if_needed(cls):
        """만료된 클라우드 세션 레코드 주기적 정리 (10분당 최대 1회)"""
        now = time.time()
        if now - cls._last_session_gc_at < 600:
            return
        cls._last_session_gc_at = now
        client = cls._get_supabase_client()
        if not client:
            return
        try:
            res = client.table("worktime_hourly_rates").select("job_title").eq(
                "hourly_rate", CLOUD_SESSIONS_RATE_SLOT
            ).execute()
            valid_rows: List[Tuple[float, str]] = []
            for row in (res.data or []):
                jt = str(row.get("job_title", "") or "")
                if not jt.startswith(CLOUD_SESSION_PREFIX):
                    continue
                rest = jt[len(CLOUD_SESSION_PREFIX):]
                sep_idx = rest.find(":")
                if sep_idx <= 0:
                    continue
                try:
                    info = json.loads(rest[sep_idx + 1:])
                    login_at = float(info.get("login_at", 0) or 0)
                    if now - login_at >= SESSION_DURATION_SECONDS:
                        client.table("worktime_hourly_rates").delete().eq(
                            "hourly_rate", CLOUD_SESSIONS_RATE_SLOT
                        ).eq("job_title", jt).execute()
                    else:
                        valid_rows.append((login_at, jt))
                except Exception:
                    pass
            # 최대 100개 초과 시 가장 오래된 세션부터 정리
            if len(valid_rows) > 100:
                valid_rows.sort(key=lambda x: x[0])
                for _, old_jt in valid_rows[:-100]:
                    client.table("worktime_hourly_rates").delete().eq(
                        "hourly_rate", CLOUD_SESSIONS_RATE_SLOT
                    ).eq("job_title", old_jt).execute()
        except Exception:
            pass

    # =========================================================
    # 2. 계정 목록 조회 및 양방향 영구 동기화 (SQLite <-> JSON <-> Supabase)
    # =========================================================
    @classmethod
    def get_all_accounts(cls, force_reload: bool = False) -> List[Dict[str, Any]]:
        """등록된 모든 관리자 계정 목록 조회 및 클라우드 자동 동기화"""
        now = time.time()
        if (
            cls._cached_accounts is not None
            and not force_reload
            and (now - cls._accounts_loaded_at < ACCOUNTS_CACHE_TTL_SECONDS)
        ):
            return list(cls._cached_accounts.values())

        cls._init_db()
        local_map: Dict[str, Dict[str, Any]] = {}

        # 1. 로컬 SQLite에서 로드
        try:
            conn = cls._get_db_conn()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM admin_accounts ORDER BY role DESC, username ASC")
            for r in cur.fetchall():
                norm_acc = cls._normalize_account_record(dict(r))
                if norm_acc:
                    local_map[norm_acc["username"].lower()] = norm_acc
            conn.close()
        except Exception:
            pass

        # 2. 로컬 JSON 병합 (동일 아이디면 updated_at 최신 우선)
        try:
            if LOCAL_ACCOUNTS_FILE.exists():
                with _FILE_LOCK:
                    with open(LOCAL_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                        file_data = json.load(f)
                if isinstance(file_data, dict):
                    for _, v in file_data.items():
                        norm_acc = cls._normalize_account_record(v)
                        if norm_acc:
                            uk = norm_acc["username"].lower()
                            existing = local_map.get(uk)
                            if not existing or norm_acc["updated_at"] > existing["updated_at"]:
                                local_map[uk] = norm_acc
        except Exception:
            pass

        # 3. 평문 비밀번호가 남아 있다면 즉시 해시 승격
        cls._migrate_plain_passwords_in_map(local_map)

        # 4. Supabase Cloud DB 조회 및 지능형 병합
        cloud_status, cloud_map, deleted_map = cls._load_accounts_from_cloud()
        accounts_map: Dict[str, Dict[str, Any]] = {}
        needs_cloud_push = False
        local_cleanup_keys: List[str] = []

        if cloud_status == "OK":
            accounts_map = dict(cloud_map)
            for uk, l_acc in local_map.items():
                # 클라우드에서 삭제된 계정(tombstone)이면 부활 차단 및 로컬 정리
                if uk != SUPER_ADMIN_USERNAME.lower() and uk in deleted_map:
                    if l_acc["updated_at"] <= deleted_map[uk]:
                        local_cleanup_keys.append(uk)
                        continue

                if uk in accounts_map:
                    if l_acc["updated_at"] > accounts_map[uk]["updated_at"] and cls._can_auto_upward_sync_account(l_acc):
                        accounts_map[uk] = l_acc
                        needs_cloud_push = True
                else:
                    if cls._can_auto_upward_sync_account(l_acc):
                        accounts_map[uk] = l_acc
                        needs_cloud_push = True

            if SUPER_ADMIN_USERNAME.lower() not in accounts_map:
                accounts_map[SUPER_ADMIN_USERNAME.lower()] = local_map.get(
                    SUPER_ADMIN_USERNAME.lower(),
                    DEFAULT_ACCOUNTS["newprim"].copy()
                )

            cls._sync_accounts_to_local(accounts_map, deleted_keys=local_cleanup_keys)
            if needs_cloud_push:
                cls._save_accounts_to_cloud(accounts_map, deleted_map)

        elif cloud_status == "EMPTY":
            # 클라우드가 아직 초기화된 적 없는 상태 -> 유효 로컬 계정을 클라우드에 최초 자동 백업
            syncable_accounts: Dict[str, Dict[str, Any]] = {}
            for uk, l_acc in local_map.items():
                if cls._can_auto_upward_sync_account(l_acc):
                    syncable_accounts[uk] = l_acc

            accounts_map = dict(local_map)
            if SUPER_ADMIN_USERNAME.lower() not in accounts_map:
                accounts_map[SUPER_ADMIN_USERNAME.lower()] = DEFAULT_ACCOUNTS["newprim"].copy()

            if syncable_accounts:
                push_target = dict(syncable_accounts)
                if SUPER_ADMIN_USERNAME.lower() not in push_target:
                    push_target[SUPER_ADMIN_USERNAME.lower()] = accounts_map[SUPER_ADMIN_USERNAME.lower()]
                cls._save_accounts_to_cloud(push_target, deleted_map)

        else:
            # 네트워크 일시 오류(ERROR) 또는 클라우드 비활성(DISABLED) 시 덮어쓰기 없이 로컬 사용
            accounts_map = dict(local_map)
            if SUPER_ADMIN_USERNAME.lower() not in accounts_map:
                accounts_map[SUPER_ADMIN_USERNAME.lower()] = DEFAULT_ACCOUNTS["newprim"].copy()

        cls._cached_accounts = accounts_map
        cls._accounts_loaded_at = time.time()
        return list(accounts_map.values())

    @classmethod
    def ensure_cloud_sync(cls):
        """앱 기동/렌더링 시 TTL 기반으로 계정 원장 클라우드 동기화를 보장"""
        cls.get_all_accounts(force_reload=False)

    @classmethod
    def _migrate_plain_passwords_in_map(cls, accounts_map: Dict[str, Dict[str, Any]]):
        """기존 평문으로 저장된 계정 비밀번호가 있으면 자동으로 PBKDF2 단방향 솔트 해시로 승격"""
        migrated = False
        now_str = cls._now_kst_str()
        for _, acc in accounts_map.items():
            pwd = acc.get("password", "")
            if pwd and not is_hashed_password(pwd):
                acc["password"] = hash_password(pwd)
                acc["updated_at"] = now_str
                migrated = True
        if migrated:
            cls._sync_accounts_to_local(accounts_map)

    # =========================================================
    # 3. 계정 등록, 수정, 삭제 (Super Admin 전용 기능)
    # =========================================================
    @classmethod
    def create_account(
        cls,
        username: str,
        password: str,
        name: str = "",
        note: str = ""
    ) -> Tuple[bool, str]:
        """
        신규 관리자(Admin) 계정 등록 (오직 Super Admin만 호출 가능)
        - PBKDF2 단방향 솔트 해시를 적용하여 로컬 SQLite + JSON + Supabase 클라우드에 즉시 저장
        """
        u = username.strip()
        p = password.strip()
        if not u or not p:
            return False, "아이디와 비밀번호를 모두 입력해주세요."

        if len(u) < 3:
            return False, "아이디는 최소 3자 이상이어야 합니다."
        if len(p) < 4:
            return False, "비밀번호는 최소 4자 이상이어야 합니다."

        accounts = cls.get_all_accounts(force_reload=True)
        if any(acc["username"].lower() == u.lower() for acc in accounts):
            return False, f"이미 존재하는 아이디입니다: {u}"

        now_str = cls._now_kst_str()
        hashed_pwd = hash_password(p)
        new_acc = {
            "username": u,
            "password": hashed_pwd,
            "name": name.strip(),
            "role": "SUPER_ADMIN" if u.lower() == SUPER_ADMIN_USERNAME.lower() else "ADMIN",
            "note": note.strip(),
            "created_at": now_str,
            "updated_at": now_str
        }

        all_dict = {acc["username"].lower(): acc for acc in accounts}
        all_dict[u.lower()] = new_acc
        cls._cached_deleted.pop(u.lower(), None)

        cls._sync_accounts_to_local(all_dict)
        cls._save_accounts_to_cloud(all_dict, cls._cached_deleted)

        cls._cached_accounts = all_dict
        cls._accounts_loaded_at = time.time()
        return True, f"✅ 관리자 계정 [{u}]이 안전하게 암호화되어 클라우드에 영구 등록되었습니다!"

    @classmethod
    def update_account_password(cls, username: str, new_password: str) -> Tuple[bool, str]:
        """비밀번호 변경 (PBKDF2 단방향 솔트 해시 적용 + 타 기기 구 세션 즉시 무효화)"""
        u = username.strip()
        p = new_password.strip()
        if len(p) < 4:
            return False, "비밀번호는 최소 4자 이상이어야 합니다."

        accounts = cls.get_all_accounts(force_reload=True)
        all_dict = {acc["username"].lower(): acc for acc in accounts}
        if u.lower() not in all_dict:
            return False, f"존재하지 않는 계정입니다: {u}"

        now_str = cls._now_kst_str()
        hashed_pwd = hash_password(p)
        new_fp = _password_fingerprint(hashed_pwd)

        all_dict[u.lower()]["password"] = hashed_pwd
        all_dict[u.lower()]["updated_at"] = now_str

        cls._sync_accounts_to_local(all_dict)
        cls._save_accounts_to_cloud(all_dict, cls._cached_deleted)

        # 현재 작업 중인 본인의 세션이면 새 비밀번호 지문으로 갱신 유지하고, 그 외 모든 구 세션은 무효화
        keep_th = None
        try:
            curr_auth = st.session_state.get("auth_user")
            if isinstance(curr_auth, dict) and str(curr_auth.get("username", "")).lower() == u.lower():
                curr_auth["pwd_fp"] = new_fp
                st.session_state["auth_user"] = curr_auth
                keep_th = curr_auth.get("token_hash")
                if keep_th:
                    cache = cls._load_session_cache()
                    if keep_th in cache:
                        cache[keep_th]["pwd_fp"] = new_fp
                        cls._save_session_cache(cache)
                    cls._save_session_to_cloud(keep_th, curr_auth)
        except Exception:
            pass

        cls._revoke_user_sessions(u, keep_token_hash=keep_th)
        cls._cached_accounts = all_dict
        cls._accounts_loaded_at = time.time()
        return True, f"✅ [{u}] 계정의 비밀번호가 안전하게 암호화되어 클라우드에 반영되었습니다!"

    @classmethod
    def delete_account(cls, username: str) -> Tuple[bool, str]:
        """계정 삭제 (newprim 본인은 삭제 불가, 삭제 즉시 Tombstone 기록 및 활성 세션 파기)"""
        u = username.strip()
        if u.lower() == SUPER_ADMIN_USERNAME.lower():
            return False, "⛔ 최고 관리자(Super Admin: newprim) 계정은 삭제할 수 없습니다."

        accounts = cls.get_all_accounts(force_reload=True)
        all_dict = {acc["username"].lower(): acc for acc in accounts}
        if u.lower() in all_dict:
            del all_dict[u.lower()]

        now_str = cls._now_kst_str()
        cls._cached_deleted[u.lower()] = now_str

        cls._sync_accounts_to_local(all_dict, deleted_keys=[u.lower()])
        cls._save_accounts_to_cloud(all_dict, cls._cached_deleted)
        cls._revoke_user_sessions(u)

        cls._cached_accounts = all_dict
        cls._accounts_loaded_at = time.time()
        return True, f"✅ [{u}] 계정이 클라우드 및 로컬에서 영구 삭제되었습니다."

    # =========================================================
    # 4. 브라우저 쿠키 연동 및 세션/권한 검증
    # =========================================================
    @staticmethod
    def _get_browser_cookie(name: str = COOKIE_NAME) -> str:
        """Streamlit 내장 st.context.cookies에서 브라우저 쿠키 읽기"""
        try:
            cookies = getattr(st.context, "cookies", None)
            if cookies is not None:
                val = cookies.get(name, "")
                return str(val or "").strip()
        except Exception:
            pass
        return ""

    @staticmethod
    def _is_valid_hex_token(token: str) -> bool:
        return bool(token) and len(token) == 32 and all(c in "0123456789abcdefABCDEF" for c in token)

    @classmethod
    def _validate_session_against_account(cls, session_info: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """세션의 사용자가 실제 존재하며 비밀번호가 변경되지 않았는지 검증"""
        username = str(session_info.get("username", "") or "").strip()
        if not username:
            return False, None

        accounts = cls.get_all_accounts(force_reload=False)
        matched = next((a for a in accounts if a["username"].lower() == username.lower()), None)
        if not matched:
            return False, None

        current_fp = _password_fingerprint(matched.get("password", ""))
        sess_fp = str(session_info.get("pwd_fp", "") or "").strip()
        if sess_fp and sess_fp != current_fp:
            return False, None

        return True, matched

    @classmethod
    def sync_browser_cookie(cls):
        """
        로그인/로그아웃에 따른 브라우저 쿠키(worklens_session) 동기화 스크립트 출력
        - about:srcdoc iframe 환경을 고려하여 parent.location.protocol 및 document.referrer로 HTTPS 판별
        - 쿠키가 실제 브라우저에 반영된 것이 확인되면 렌더링 중단(0px 오버헤드)
        """
        cls.ensure_cloud_sync()

        try:
            pending = st.session_state.get("_pending_auth_cookie")
        except Exception:
            return

        if not pending or not isinstance(pending, tuple) or len(pending) < 2:
            return

        action, target_token = pending[0], str(pending[1] or "")
        current_cookie = cls._get_browser_cookie(COOKIE_NAME)

        if action == "set" and target_token:
            if current_cookie == target_token:
                st.session_state.pop("_pending_auth_cookie", None)
                return
            if not cls._is_valid_hex_token(target_token):
                st.session_state.pop("_pending_auth_cookie", None)
                return
            max_age = int(SESSION_DURATION_SECONDS)
            js_code = f"""
            <script>
            (function() {{
                var isHttps = false;
                try {{ isHttps = (window.parent.location.protocol === 'https:'); }}
                catch (e) {{ isHttps = (document.referrer || '').indexOf('https:') === 0; }}
                var attr = '; path=/; max-age={max_age}' + (isHttps ? '; SameSite=None; Secure' : '; SameSite=Lax');
                var cookieStr = '{COOKIE_NAME}={target_token}' + attr;
                try {{ window.parent.document.cookie = cookieStr; }} catch (e) {{}}
                try {{ document.cookie = cookieStr; }} catch (e) {{}}
            }})();
            </script>
            """
            components.html(js_code, height=0, width=0)

        elif action == "clear":
            if not current_cookie:
                st.session_state.pop("_pending_auth_cookie", None)
                return
            js_code = f"""
            <script>
            (function() {{
                var isHttps = false;
                try {{ isHttps = (window.parent.location.protocol === 'https:'); }}
                catch (e) {{ isHttps = (document.referrer || '').indexOf('https:') === 0; }}
                var base = '{COOKIE_NAME}=; path=/; max-age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT';
                var variants = [
                    base + (isHttps ? '; SameSite=None; Secure' : '; SameSite=Lax'),
                    base + '; SameSite=Lax'
                ];
                for (var i = 0; i < variants.length; i++) {{
                    try {{ window.parent.document.cookie = variants[i]; }} catch (e) {{}}
                    try {{ document.cookie = variants[i]; }} catch (e) {{}}
                }}
            }})();
            </script>
            """
            components.html(js_code, height=0, width=0)

    @classmethod
    def is_authenticated(cls) -> bool:
        """현재 사용자가 유효 기간(기본 7일) 내에 로그인된 유효한 사용자인지 검증 및 자동 복원"""
        now = time.time()

        # URL에 혹시 남아 있을 수 있는 레거시 session_token 파라미터는 즉시 추출 후 주소창에서 무조건 제거
        query_token = ""
        try:
            if "session_token" in st.query_params:
                query_token = str(st.query_params.get("session_token", "") or "").strip()
                del st.query_params["session_token"]
        except Exception:
            pass

        # 1. Streamlit session_state 검사
        if "auth_user" in st.session_state:
            auth_info = st.session_state["auth_user"]
            if auth_info and isinstance(auth_info, dict):
                login_at = float(auth_info.get("login_at", 0) or 0)
                if now - login_at < SESSION_DURATION_SECONDS:
                    valid_acc, matched_acc = cls._validate_session_against_account(auth_info)
                    if not valid_acc or not matched_acc:
                        cls.logout()
                        return False

                    # 배포 전 생성된 활성 세션의 지문/쿠키/클라우드 세션 자동 백필 보호
                    token = str(auth_info.get("token", "") or "").strip()
                    token_hash = str(auth_info.get("token_hash", "") or (cls._hash_token(token) if token else "")).strip()
                    curr_fp = _password_fingerprint(matched_acc.get("password", ""))
                    if not auth_info.get("pwd_fp"):
                        auth_info["pwd_fp"] = curr_fp
                        st.session_state["auth_user"] = auth_info

                    if token and cls._is_valid_hex_token(token):
                        if cls._get_browser_cookie(COOKIE_NAME) != token and "_pending_auth_cookie" not in st.session_state:
                            st.session_state["_pending_auth_cookie"] = ("set", token)
                        if token_hash and not st.session_state.get("_cloud_session_backed_up"):
                            cls._save_session_to_cloud(token_hash, auth_info)
                            st.session_state["_cloud_session_backed_up"] = True
                    return True
                else:
                    cls.logout()
                    return False

        # 로그아웃 직후(브라우저 JS가 아직 쿠키를 지우기 전 패스)에는 쿠키 자동 복원 차단
        pending = st.session_state.get("_pending_auth_cookie")
        if isinstance(pending, tuple) and len(pending) >= 1 and pending[0] == "clear":
            return False

        # 2. 브라우저 쿠키(worklens_session) 또는 1회성 레거시 쿼리 토큰으로 세션 복원
        token = cls._get_browser_cookie(COOKIE_NAME) or query_token
        if cls._is_valid_hex_token(token):
            token_hash = cls._hash_token(token)
            if token_hash == st.session_state.get("_logged_out_token_hash"):
                return False

            # 로컬 캐시 조회 -> 미존재 시(컨테이너 재부팅 등) Supabase -99994 클라우드 슬롯 조회
            cache = cls._load_session_cache()
            s_info = cache.get(token_hash) or cache.get(token)
            loaded_from_cloud = False
            if not s_info:
                s_info = cls._get_session_from_cloud(token_hash)
                loaded_from_cloud = bool(s_info)

            if isinstance(s_info, dict):
                login_at = float(s_info.get("login_at", 0) or 0)
                if now - login_at < SESSION_DURATION_SECONDS:
                    valid_acc, matched_acc = cls._validate_session_against_account(s_info)
                    if valid_acc and matched_acc:
                        role = "SUPER_ADMIN" if matched_acc["username"].lower() == SUPER_ADMIN_USERNAME.lower() else "ADMIN"
                        restored_info = {
                            "username": matched_acc["username"],
                            "name": matched_acc.get("name", ""),
                            "role": role,
                            "login_at": login_at,
                            "token_hash": token_hash,
                            "pwd_fp": _password_fingerprint(matched_acc.get("password", ""))
                        }
                        st.session_state["auth_user"] = {**restored_info, "token": token}
                        st.session_state["_cloud_session_backed_up"] = True
                        if loaded_from_cloud:
                            cache[token_hash] = restored_info
                            cls._save_session_cache(cache)
                        if cls._get_browser_cookie(COOKIE_NAME) != token:
                            st.session_state["_pending_auth_cookie"] = ("set", token)
                        return True

            # 만료되었거나 무효화된 토큰 쿠키 정리
            if token_hash in cache or token in cache:
                cache.pop(token_hash, None)
                cache.pop(token, None)
                cls._save_session_cache(cache)
            st.session_state["_pending_auth_cookie"] = ("clear", "")

        return False

    @classmethod
    def get_current_user(cls) -> Optional[str]:
        """현재 로그인된 사용자명 반환"""
        if cls.is_authenticated():
            auth_info = st.session_state.get("auth_user", {})
            return auth_info.get("username", None)
        return None

    @classmethod
    def get_current_user_display_name(cls) -> str:
        """현재 로그인된 사용자의 표시 이름(이름 또는 사용자명) 반환"""
        if cls.is_authenticated():
            auth_info = st.session_state.get("auth_user", {})
            name = (auth_info.get("name") or "").strip()
            username = (auth_info.get("username") or "").strip()
            if name and username:
                return f"{name} ({username})"
            return name or username or "관리자"
        return ""

    @classmethod
    def get_current_role(cls) -> str:
        """
        현재 사용자의 권한 반환:
        - newprim: 'SUPER_ADMIN'
        - 그 외 로그인 사용자: 'ADMIN'
        - 미로그인: 'GUEST'
        """
        if cls.is_authenticated():
            u = cls.get_current_user()
            if u and u.strip().lower() == SUPER_ADMIN_USERNAME.lower():
                return "SUPER_ADMIN"
            return "ADMIN"
        return "GUEST"

    @classmethod
    def is_super_admin(cls) -> bool:
        """
        현재 로그인 사용자가 최고 관리자(Super Admin: newprim)인지 여부 반환
        - 반드시 인증되어 있어야 하며, 아이디가 'newprim'인 경우에만 True
        - 미로그인(GUEST) 또는 일반 관리자(ADMIN)는 무조건 False 반환
        """
        if not cls.is_authenticated():
            return False
        u = cls.get_current_user()
        if not u:
            return False
        return u.strip().lower() == SUPER_ADMIN_USERNAME.lower()

    # =========================================================
    # 5. 로그인 및 로그아웃 (Brute Force 무차별 대입 방어)
    # =========================================================
    @classmethod
    def is_account_locked(cls, username: str) -> Tuple[bool, int]:
        """계정 일시 잠금 여부 및 남은 잠금 시간(초) 반환"""
        u = username.strip().lower()
        now = time.time()
        record = cls._failed_attempts.get(u)
        if not record:
            return False, 0

        lock_until = record.get("lock_until", 0)
        if lock_until > now:
            return True, int(lock_until - now)
        elif lock_until > 0 and now >= lock_until:
            cls._failed_attempts.pop(u, None)
            return False, 0
        return False, 0

    @classmethod
    def record_failed_attempt(cls, username: str) -> Tuple[int, int]:
        """로그인 실패 횟수 기록 (5회 도달 시 3분 잠금), (현재 실패횟수, 남은 시도 가능 횟수) 반환"""
        u = username.strip().lower()
        now = time.time()
        record = cls._failed_attempts.setdefault(u, {"count": 0, "lock_until": 0})
        record["count"] += 1
        record["last_attempt"] = now

        if record["count"] >= cls.MAX_FAILED_ATTEMPTS:
            record["lock_until"] = now + cls.LOCKOUT_DURATION_SECONDS
            return record["count"], 0

        return record["count"], cls.MAX_FAILED_ATTEMPTS - record["count"]

    @classmethod
    def reset_failed_attempts(cls, username: str):
        """로그인 성공 시 실패 기록 초기화"""
        u = username.strip().lower()
        cls._failed_attempts.pop(u, None)

    @classmethod
    def login_with_status(cls, username: str, password: str) -> Tuple[bool, str]:
        """사용자 로그인 처리 및 상태 메시지 반환 (클라우드 세션 & 브라우저 쿠키 연동)"""
        u = username.strip()
        p = password.strip()
        if not u or not p:
            return False, "아이디와 비밀번호를 모두 입력해주세요."

        # 1. 계정 잠금 상태 검사
        is_locked, rem_sec = cls.is_account_locked(u)
        if is_locked:
            return False, f"⛔ 로그인 {cls.MAX_FAILED_ATTEMPTS}회 연속 실패로 계정이 일시 잠금되었습니다. ({rem_sec}초 후 다시 시도)"

        # 전체 계정 목록 최신 로드
        accounts = cls.get_all_accounts(force_reload=True)
        matched_acc = None
        for acc in accounts:
            if acc["username"].lower() == u.lower() and verify_password(p, acc.get("password", "")):
                matched_acc = acc
                break

        if matched_acc:
            cls.reset_failed_attempts(u)

            # 기존 저장 비밀번호가 평문이었다면 단방향 솔트 해시로 승격 저장
            if not is_hashed_password(matched_acc.get("password", "")):
                cls.update_account_password(matched_acc["username"], p)
                accounts = cls.get_all_accounts(force_reload=True)
                matched_acc = next((a for a in accounts if a["username"].lower() == u.lower()), matched_acc)

            now = time.time()
            token = secrets.token_hex(16)
            token_hash = cls._hash_token(token)
            role = "SUPER_ADMIN" if matched_acc["username"].lower() == SUPER_ADMIN_USERNAME.lower() else "ADMIN"
            pwd_fp = _password_fingerprint(matched_acc.get("password", ""))

            session_info = {
                "username": matched_acc["username"],
                "name": matched_acc.get("name", ""),
                "role": role,
                "login_at": now,
                "token_hash": token_hash,
                "pwd_fp": pwd_fp
            }

            # 1. Streamlit 세션 및 브라우저 쿠키 예약 저장
            st.session_state.pop("_logged_out_token_hash", None)
            st.session_state["auth_user"] = {**session_info, "token": token}
            st.session_state["_pending_auth_cookie"] = ("set", token)
            st.session_state["_cloud_session_backed_up"] = True

            # 2. 로컬 캐시 파일 및 Supabase 클라우드(-99994) 동시 저장 (원문 토큰은 절대 디스크/DB 미저장)
            cache = cls._load_session_cache()
            cache[token_hash] = session_info
            cls._save_session_cache(cache)
            cls._save_session_to_cloud(token_hash, session_info)

            # 3. 브라우저 쿼리 파라미터 정리 (주소창 URL 세션 토큰 노출 차단)
            try:
                if "session_token" in st.query_params:
                    del st.query_params["session_token"]
            except Exception:
                pass
            return True, f"🎉 로그인 성공! 모든 관리자 권한이 활성화되었습니다. ({SESSION_DAYS}일간 유지)"

        # 실패 시 카운트 증가
        count, rem = cls.record_failed_attempt(u)
        if rem <= 0:
            return False, f"⛔ 비밀번호를 {cls.MAX_FAILED_ATTEMPTS}회 연속 잘못 입력하여 계정이 {cls.LOCKOUT_DURATION_SECONDS // 60}분간 잠금되었습니다."
        return False, f"⚠️ 아이디 또는 비밀번호가 올바르지 않습니다. (남은 시도: {rem}회)"

    @classmethod
    def login(cls, username: str, password: str) -> bool:
        """하위 호환성을 위한 bool 반환 login 메서드"""
        success, _ = cls.login_with_status(username, password)
        return success

    @classmethod
    def logout(cls):
        """로그아웃 처리 (로컬 + 클라우드 세션 즉시 파기 및 브라우저 쿠키 삭제 예약)"""
        token = None
        token_hash = None
        if "auth_user" in st.session_state:
            auth_obj = st.session_state.get("auth_user") or {}
            token = auth_obj.get("token")
            token_hash = auth_obj.get("token_hash")
            del st.session_state["auth_user"]

        if not token:
            token = cls._get_browser_cookie(COOKIE_NAME)
        if not token:
            try:
                token = str(st.query_params.get("session_token", "") or "").strip()
            except Exception:
                token = None

        if token and not token_hash:
            token_hash = cls._hash_token(token)

        if token or token_hash:
            cache = cls._load_session_cache()
            changed = False
            if token_hash and token_hash in cache:
                del cache[token_hash]
                changed = True
            if token and token in cache:
                del cache[token]
                changed = True
            if changed:
                cls._save_session_cache(cache)

        if token_hash:
            cls._delete_session_from_cloud(token_hash)
            st.session_state["_logged_out_token_hash"] = token_hash

        st.session_state.pop("_cloud_session_backed_up", None)
        st.session_state["_pending_auth_cookie"] = ("clear", "")

        try:
            if "session_token" in st.query_params:
                del st.query_params["session_token"]
        except Exception:
            pass

        st.session_state["current_page"] = "🏠 실시간 분석 대시보드"
