"""
시스템 관리자 인증 및 계정 권한(Super Admin / Admin) 관리 매니저
- newprim: Super Admin (모든 메뉴 및 시스템 관리, 계정 등록 권한 보유)
- 그 외 계정: Admin (일반 관리 권한, 시스템 관리 메뉴 접근 불가)
- 3중 영구 저장: 로컬 SQLite + 로컬 JSON + Supabase Cloud DB
"""

import json
import time
import sqlite3
import secrets
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import streamlit as st

# 세션 유지 시간: 24시간 (초)
SESSION_DURATION_SECONDS = 24 * 3600

# 프로젝트 루트 및 파일 경로
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SESSION_CACHE_FILE = DATA_DIR / ".session_cache.json"
LOCAL_ACCOUNTS_FILE = DATA_DIR / "admin_accounts.json"

SUPER_ADMIN_USERNAME = "newprim"
DEFAULT_SUPER_ADMIN_PWD = "newprim1"

DEFAULT_ACCOUNTS = {
    "newprim": {
        "username": "newprim",
        "password": DEFAULT_SUPER_ADMIN_PWD,
        "name": "최고 관리자",
        "role": "SUPER_ADMIN",
        "note": "시스템 최고 관리자 (전체 권한)",
        "created_at": "2026-09-01 00:00:00"
    }
}


class AuthManager:
    _cached_accounts: Optional[Dict[str, Dict[str, Any]]] = None

    # =========================================================
    # 1. 로컬 SQLite & JSON 저장소 초기화
    # =========================================================
    @classmethod
    def _init_db(cls):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            from ..config import config
            db_path = config.LOCAL_DB_PATH
        except Exception:
            db_path = DATA_DIR / "worklog.db"
        
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
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)
            # 기본 newprim 계정 보장
            cur.execute("""
                INSERT OR IGNORE INTO admin_accounts (username, password, name, role, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
            """, ("newprim", DEFAULT_SUPER_ADMIN_PWD, "최고 관리자", "SUPER_ADMIN", "시스템 최고 관리자"))
            conn.commit()
            conn.close()
        except Exception:
            pass

    @classmethod
    def _get_db_conn(cls):
        try:
            from ..config import config
            db_path = config.LOCAL_DB_PATH
        except Exception:
            db_path = DATA_DIR / "worklog.db"
        return sqlite3.connect(str(db_path))

    @staticmethod
    def _load_session_cache() -> Dict[str, Any]:
        """로컬 파일 기반 세션 캐시 로드"""
        if SESSION_CACHE_FILE.exists():
            try:
                with open(SESSION_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    @staticmethod
    def _save_session_cache(cache: Dict[str, Any]):
        """로컬 파일 기반 세션 캐시 저장"""
        SESSION_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(SESSION_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # =========================================================
    # 2. 계정 목록 조회 및 동기화 (SQLite -> JSON -> Supabase)
    # =========================================================
    @classmethod
    def get_all_accounts(cls, force_reload: bool = False) -> List[Dict[str, Any]]:
        """등록된 모든 관리자 계정 목록 조회"""
        if cls._cached_accounts is not None and not force_reload:
            return list(cls._cached_accounts.values())

        cls._init_db()
        accounts_map: Dict[str, Dict[str, Any]] = {}

        # 0. 기본 newprim 계정 탑재
        accounts_map["newprim"] = DEFAULT_ACCOUNTS["newprim"].copy()

        # 1. 로컬 SQLite에서 로드
        try:
            conn = cls._get_db_conn()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM admin_accounts ORDER BY role DESC, username ASC")
            for r in cur.fetchall():
                rd = dict(r)
                un = rd.get("username", "").strip()
                if un:
                    accounts_map[un.lower()] = {
                        "username": un,
                        "password": rd.get("password", ""),
                        "name": rd.get("name", ""),
                        "role": "SUPER_ADMIN" if un.lower() == SUPER_ADMIN_USERNAME.lower() else rd.get("role", "ADMIN"),
                        "note": rd.get("note", ""),
                        "created_at": rd.get("created_at", ""),
                        "updated_at": rd.get("updated_at", "")
                    }
            conn.close()
        except Exception:
            pass

        # 2. 로컬 JSON fallback
        try:
            if LOCAL_ACCOUNTS_FILE.exists():
                with open(LOCAL_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    if isinstance(file_data, dict):
                        for k, v in file_data.items():
                            if k.lower() not in accounts_map:
                                accounts_map[k.lower()] = v
        except Exception:
            pass

        # 3. Supabase Cloud DB 동기화 시도
        try:
            from ..database.supabase_client import db_manager
            if db_manager.use_supabase and db_manager.supabase:
                res = db_manager.supabase.table("worktime_admin_accounts").select("*").execute()
                if res.data:
                    for row in res.data:
                        un = str(row.get("username", "")).strip()
                        if un:
                            accounts_map[un.lower()] = {
                                "username": un,
                                "password": row.get("password", ""),
                                "name": row.get("name", ""),
                                "role": "SUPER_ADMIN" if un.lower() == SUPER_ADMIN_USERNAME.lower() else row.get("role", "ADMIN"),
                                "note": row.get("note", ""),
                                "created_at": str(row.get("created_at", "")),
                                "updated_at": str(row.get("updated_at", ""))
                            }
        except Exception:
            pass

        cls._cached_accounts = accounts_map
        return list(accounts_map.values())

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

        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. SQLite 저장
        cls._init_db()
        try:
            conn = cls._get_db_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO admin_accounts (username, password, name, role, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (u, p, name.strip(), "ADMIN", note.strip(), now_str, now_str))
            conn.commit()
            conn.close()
        except Exception as e:
            return False, f"로컬 DB 저장 오류: {e}"

        # 2. 로컬 JSON 저장
        try:
            all_dict = {acc["username"].lower(): acc for acc in cls.get_all_accounts(force_reload=True)}
            all_dict[u.lower()] = {
                "username": u, "password": p, "name": name.strip(),
                "role": "ADMIN", "note": note.strip(), "created_at": now_str, "updated_at": now_str
            }
            with open(LOCAL_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                json.dump(all_dict, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # 3. Supabase Cloud DB 동기화
        try:
            from ..database.supabase_client import db_manager
            if db_manager.use_supabase and db_manager.supabase:
                db_manager.supabase.table("worktime_admin_accounts").upsert({
                    "username": u, "password": p, "name": name.strip(),
                    "role": "ADMIN", "note": note.strip(), "updated_at": now_str
                }, on_conflict="username").execute()
        except Exception:
            pass

        cls._cached_accounts = None
        return True, f"✅ 관리자 계정 [{u}]이 성공적으로 등록되었습니다!"

    @classmethod
    def update_account_password(cls, username: str, new_password: str) -> Tuple[bool, str]:
        """비밀번호 변경"""
        u = username.strip()
        p = new_password.strip()
        if len(p) < 4:
            return False, "비밀번호는 최소 4자 이상이어야 합니다."

        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            conn = cls._get_db_conn()
            cur = conn.cursor()
            cur.execute("UPDATE admin_accounts SET password = ?, updated_at = ? WHERE username = ?", (p, now_str, u))
            conn.commit()
            conn.close()
        except Exception as e:
            return False, f"비밀번호 변경 오류: {e}"

        try:
            all_dict = {acc["username"].lower(): acc for acc in cls.get_all_accounts(force_reload=True)}
            if u.lower() in all_dict:
                all_dict[u.lower()]["password"] = p
                all_dict[u.lower()]["updated_at"] = now_str
                with open(LOCAL_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(all_dict, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        try:
            from ..database.supabase_client import db_manager
            if db_manager.use_supabase and db_manager.supabase:
                db_manager.supabase.table("worktime_admin_accounts").update({
                    "password": p, "updated_at": now_str
                }).eq("username", u).execute()
        except Exception:
            pass

        cls._cached_accounts = None
        return True, f"✅ [{u}] 계정의 비밀번호가 성공적으로 변경되었습니다!"

    @classmethod
    def delete_account(cls, username: str) -> Tuple[bool, str]:
        """계정 삭제 (newprim 본인은 삭제 불가)"""
        u = username.strip()
        if u.lower() == SUPER_ADMIN_USERNAME.lower():
            return False, "⛔ 최고 관리자(Super Admin: newprim) 계정은 삭제할 수 없습니다."

        try:
            conn = cls._get_db_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM admin_accounts WHERE username = ?", (u,))
            conn.commit()
            conn.close()
        except Exception as e:
            return False, f"계정 삭제 오류: {e}"

        try:
            all_dict = {acc["username"].lower(): acc for acc in cls.get_all_accounts(force_reload=True)}
            if u.lower() in all_dict:
                del all_dict[u.lower()]
                with open(LOCAL_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(all_dict, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        try:
            from ..database.supabase_client import db_manager
            if db_manager.use_supabase and db_manager.supabase:
                db_manager.supabase.table("worktime_admin_accounts").delete().eq("username", u).execute()
        except Exception:
            pass

        cls._cached_accounts = None
        return True, f"✅ [{u}] 계정이 성공적으로 삭제되었습니다."

    # =========================================================
    # 4. 세션 및 권한 검증 (Super Admin vs Admin)
    # =========================================================
    @classmethod
    def is_authenticated(cls) -> bool:
        """현재 사용자가 24시간 내에 로그인된 유효한 사용자인지 검증"""
        now = time.time()

        # 1. Streamlit session_state 검사
        if "auth_user" in st.session_state:
            auth_info = st.session_state["auth_user"]
            if auth_info and isinstance(auth_info, dict):
                login_at = auth_info.get("login_at", 0)
                if now - login_at < SESSION_DURATION_SECONDS:
                    return True
                else:
                    cls.logout()
                    return False

        # 2. 브라우저 쿼리 파라미터 기반 세션 토큰 복원 (새로고침 / 탭 복원 시)
        token = st.query_params.get("session_token")
        if token:
            cache = cls._load_session_cache()
            if token in cache:
                s_info = cache[token]
                login_at = s_info.get("login_at", 0)
                if now - login_at < SESSION_DURATION_SECONDS:
                    st.session_state["auth_user"] = s_info
                    return True
                else:
                    del cache[token]
                    cls._save_session_cache(cache)
                    if "session_token" in st.query_params:
                        del st.query_params["session_token"]

        return False

    @classmethod
    def get_current_user(cls) -> Optional[str]:
        """현재 로그인된 사용자명 반환"""
        if cls.is_authenticated():
            auth_info = st.session_state.get("auth_user", {})
            return auth_info.get("username", None)
        return None

    @classmethod
    def get_current_role(cls) -> str:
        """
        현재 사용자의 권한 반환:
        - newprim: 'SUPER_ADMIN'
        - 그 외: 'ADMIN' (미로그인 시 'GUEST')
        """
        if cls.is_authenticated():
            u = cls.get_current_user()
            if u and u.lower() == SUPER_ADMIN_USERNAME.lower():
                return "SUPER_ADMIN"
            auth_info = st.session_state.get("auth_user", {})
            return auth_info.get("role", "ADMIN")
        return "GUEST"

    @classmethod
    def is_super_admin(cls) -> bool:
        """
        현재 로그인 사용자가 최고 관리자(Super Admin: newprim)인지 여부 반환
        - newprim만 True 반환 (시스템 관리 메뉴 및 계정 등록 메뉴 열람 가능)
        - 다른 계정은 False 반환
        """
        return cls.get_current_role() == "SUPER_ADMIN"

    # =========================================================
    # 5. 로그인 및 로그아웃
    # =========================================================
    @classmethod
    def login(cls, username: str, password: str) -> bool:
        """사용자 로그인 처리 및 24시간 세션 토큰 발급"""
        u = username.strip()
        p = password.strip()

        # 전체 계정 목록 로드
        accounts = cls.get_all_accounts(force_reload=True)
        matched_acc = None
        for acc in accounts:
            if acc["username"].lower() == u.lower() and acc["password"] == p:
                matched_acc = acc
                break

        if matched_acc:
            now = time.time()
            token = secrets.token_hex(16)
            role = "SUPER_ADMIN" if matched_acc["username"].lower() == SUPER_ADMIN_USERNAME.lower() else "ADMIN"

            session_info = {
                "username": matched_acc["username"],
                "name": matched_acc.get("name", ""),
                "role": role,
                "login_at": now,
                "token": token
            }

            # 1. Streamlit 세션 저장
            st.session_state["auth_user"] = session_info

            # 2. 로컬 캐시 파일 저장 (새로고침 대응)
            cache = cls._load_session_cache()
            cache = {k: v for k, v in cache.items() if now - v.get("login_at", 0) < SESSION_DURATION_SECONDS}
            cache[token] = session_info
            cls._save_session_cache(cache)

            # 3. 브라우저 쿼리 파라미터에 세션 토큰 저장
            st.query_params["session_token"] = token
            return True

        return False

    @classmethod
    def logout(cls):
        """로그아웃 처리"""
        token = None
        if "auth_user" in st.session_state:
            token = st.session_state["auth_user"].get("token")
            del st.session_state["auth_user"]

        if not token:
            token = st.query_params.get("session_token")

        if token:
            cache = cls._load_session_cache()
            if token in cache:
                del cache[token]
                cls._save_session_cache(cache)

        if "session_token" in st.query_params:
            del st.query_params["session_token"]

        st.session_state["current_page"] = "🏠 실시간 분석 대시보드"
