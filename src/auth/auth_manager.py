"""
시스템 관리자 인증 및 24시간 세션 매니저
"""

import json
import time
import hashlib
import secrets
from pathlib import Path
from typing import Optional, Dict, Any
import streamlit as st

# 세션 유지 시간: 24시간 (초)
SESSION_DURATION_SECONDS = 24 * 3600

# 프로젝트 루트 및 세션 캐시 파일 경로
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SESSION_CACHE_FILE = PROJECT_ROOT / "data" / ".session_cache.json"

# 관리자 계정 정보
ADMIN_CREDENTIALS = {
    "newprim": "newprim1"
}


class AuthManager:
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

    @classmethod
    def is_authenticated(cls) -> bool:
        """
        현재 사용자가 24시간 내에 로그인된 유효한 관리자인지 검증
        """
        now = time.time()

        # 1. Streamlit session_state 검사
        if "auth_user" in st.session_state:
            auth_info = st.session_state["auth_user"]
            if auth_info and isinstance(auth_info, dict):
                login_at = auth_info.get("login_at", 0)
                if now - login_at < SESSION_DURATION_SECONDS:
                    return True
                else:
                    # 세션 만료
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
                    # 세션 복원
                    st.session_state["auth_user"] = s_info
                    return True
                else:
                    # 만료된 토큰 정리
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
            return auth_info.get("username", "newprim")
        return None

    @classmethod
    def login(cls, username: str, password: str) -> bool:
        """
        사용자 로그인 처리 및 24시간 세션 토큰 발급
        """
        u = username.strip()
        p = password.strip()

        if u in ADMIN_CREDENTIALS and ADMIN_CREDENTIALS[u] == p:
            now = time.time()
            token = secrets.token_hex(16)

            session_info = {
                "username": u,
                "login_at": now,
                "token": token
            }

            # 1. Streamlit 세션 저장
            st.session_state["auth_user"] = session_info

            # 2. 로컬 캐시 파일 저장 (새로고침 대응)
            cache = cls._load_session_cache()
            # 만료된 오래된 세션 정리
            cache = {k: v for k, v in cache.items() if now - v.get("login_at", 0) < SESSION_DURATION_SECONDS}
            cache[token] = session_info
            cls._save_session_cache(cache)

            # 3. 브라우저 쿼리 파라미터에 세션 토큰 저장
            st.query_params["session_token"] = token

            return True

        return False

    @classmethod
    def logout(cls):
        """
        로그아웃 처리
        """
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
