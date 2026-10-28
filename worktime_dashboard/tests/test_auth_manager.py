# -*- coding: utf-8 -*-
import os
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# 테스트 실행 중 실제 클라우드 DB 접근 원천 차단 및 불필요한 Streamlit bare-mode 경고 억제
os.environ["WORKLENS_DISABLE_CLOUD_AUTH_SYNC"] = "1"
logging.getLogger("streamlit").setLevel(logging.CRITICAL)

import streamlit as st
from src.auth import auth_manager as am
from src.auth.auth_manager import (
    hash_password,
    verify_password,
    is_hashed_password,
    AuthManager,
    CLOUD_ACCOUNTS_RATE_SLOT,
    CLOUD_SESSIONS_RATE_SLOT,
)


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, store, table_name):
        self.store = store
        self.table_name = table_name
        self._op = "select"
        self._payload = None
        self._on_conflict = None
        self._filters = []

    def select(self, *_args, **_kwargs):
        self._op = "select"
        return self

    def upsert(self, payload, on_conflict=None):
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        return self

    def like(self, col, pattern):
        self._filters.append(("like", col, pattern))
        return self

    def ilike(self, col, pattern):
        self._filters.append(("ilike", col, pattern))
        return self

    def _matches(self, row):
        for kind, col, val in self._filters:
            rv = row.get(col)
            if kind == "eq" and rv != val:
                return False
            if kind == "neq" and rv == val:
                return False
            if kind == "like":
                prefix = str(val).rstrip("%")
                if not str(rv or "").startswith(prefix):
                    return False
            if kind == "ilike":
                if str(rv or "").lower() != str(val or "").lower():
                    return False
        return True

    def execute(self):
        if self.table_name == "worktime_admin_accounts":
            # 실제 프로덕션과 동일하게 전용 테이블 미생성(PGRST205) 환경 시뮬레이션
            raise RuntimeError("PGRST205: table worktime_admin_accounts not found")

        rows = self.store.setdefault(self.table_name, [])
        if self._op == "select":
            return _FakeResponse([dict(r) for r in rows if self._matches(r)])
        if self._op == "upsert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            key_col = self._on_conflict or "job_title"
            for item in items:
                replaced = False
                for idx, r in enumerate(rows):
                    if r.get(key_col) == item.get(key_col):
                        rows[idx] = dict(item)
                        replaced = True
                        break
                if not replaced:
                    rows.append(dict(item))
            return _FakeResponse(items)
        if self._op == "delete":
            kept = [r for r in rows if not self._matches(r)]
            deleted = [r for r in rows if self._matches(r)]
            self.store[self.table_name] = kept
            return _FakeResponse(deleted)
        return _FakeResponse([])


class _FakeSupabaseClient:
    def __init__(self):
        self.store = {"worktime_hourly_rates": []}

    def table(self, name):
        return _FakeQuery(self.store, name)


class TestAuthSecurity(unittest.TestCase):
    """관리자 인증, 클라우드 영구 동기화, 7일 쿠키 세션 복원 및 보안 단위 테스트"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)
        self.db_file = self.tmp_path / "worklog.db"
        self.accounts_json = self.tmp_path / "admin_accounts.json"
        self.session_json = self.tmp_path / ".session_cache.json"
        self.fake_cloud = _FakeSupabaseClient()

        AuthManager._failed_attempts.clear()
        AuthManager._cached_accounts = None
        AuthManager._cached_deleted = {}
        AuthManager._accounts_loaded_at = 0.0
        AuthManager._negative_token_cache.clear()
        st.session_state.clear()

        self._patches = [
            patch.object(am, "DATA_DIR", self.tmp_path),
            patch.object(am, "LOCAL_ACCOUNTS_FILE", self.accounts_json),
            patch.object(am, "SESSION_CACHE_FILE", self.session_json),
            patch.object(AuthManager, "_get_db_path", return_value=self.db_file),
            patch.object(AuthManager, "_is_cloud_sync_disabled", return_value=False),
            patch.object(AuthManager, "_get_supabase_client", return_value=self.fake_cloud),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        st.session_state.clear()
        self._tmpdir.cleanup()

    def test_password_hash_and_verify(self):
        pwd = "SecretPassword123!"
        hashed = hash_password(pwd)

        self.assertTrue(is_hashed_password(hashed))
        self.assertTrue(verify_password(pwd, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

    def test_brute_force_lockout(self):
        test_user = "test_attacker"

        for i in range(4):
            count, _ = AuthManager.record_failed_attempt(test_user)
            self.assertEqual(count, i + 1)
            self.assertFalse(AuthManager.is_account_locked(test_user)[0])

        count, rem = AuthManager.record_failed_attempt(test_user)
        self.assertEqual(count, 5)
        self.assertEqual(rem, 0)

        is_locked, remaining_sec = AuthManager.is_account_locked(test_user)
        self.assertTrue(is_locked)
        self.assertGreater(remaining_sec, 0)

        AuthManager.reset_failed_attempts(test_user)
        self.assertFalse(AuthManager.is_account_locked(test_user)[0])

    def test_upward_cloud_backup_and_container_reboot_recovery(self):
        """
        [핵심 검증]
        1) 클라우드가 비어 있는 상태에서 컨테이너 디스크에 변경된 newprim 비밀번호 및 신규 관리자 계정이 있을 때
           ensure_cloud_sync()가 유실 없이 클라우드(-99995)로 자동 영구 백업하는지 확인
        2) 컨테이너 리부트(로컬 DB/JSON 완전 삭제) 후에도 기본 비밀번호로 덮어써지지 않고
           클라우드에서 모든 계정과 변경된 비밀번호가 100% 복원되는지 확인
        """
        # 1. 클라우드가 비어 있는 초기 상태에서 로컬에만 변경된 계정 준비
        am._atomic_write_json(self.accounts_json, {
            "newprim": {
                "username": "newprim",
                "password": hash_password("ChangedSuperPwd2026!"),
                "name": "최고 관리자",
                "role": "SUPER_ADMIN",
                "note": "비번 변경 완료",
                "created_at": "2026-10-28 14:50:00",
                "updated_at": "2026-10-28 14:55:00"
            },
            "ops_admin": {
                "username": "ops_admin",
                "password": hash_password("OpsPass99!"),
                "name": "운영관리자",
                "role": "ADMIN",
                "note": "신규 생성 계정",
                "created_at": "2026-10-28 14:56:00",
                "updated_at": "2026-10-28 14:56:00"
            }
        })

        AuthManager.ensure_cloud_sync()

        # 클라우드 -99995 슬롯에 정상 업로드되었는지 확인
        cloud_rows = [
            r for r in self.fake_cloud.store["worktime_hourly_rates"]
            if r.get("hourly_rate") == CLOUD_ACCOUNTS_RATE_SLOT
        ]
        self.assertEqual(len(cloud_rows), 1)

        # 2. 컨테이너 리부트 시뮬레이션: 로컬 SQLite, JSON, 메모리 캐시 전면 삭제
        if self.db_file.exists():
            self.db_file.unlink()
        if self.accounts_json.exists():
            self.accounts_json.unlink()
        AuthManager._cached_accounts = None
        AuthManager._accounts_loaded_at = 0.0

        # 리부트 후 기본 초기 비밀번호(admin1234!)는 거부되고 변경된 비밀번호 및 신규 계정이 모두 유지되어야 함
        self.assertFalse(AuthManager.login("newprim", "admin1234!"))
        AuthManager.reset_failed_attempts("newprim")
        self.assertTrue(AuthManager.login("newprim", "ChangedSuperPwd2026!"))
        AuthManager.logout()
        self.assertTrue(AuthManager.login("ops_admin", "OpsPass99!"))

    def test_stale_windows_dev_accounts_do_not_pollute_cloud(self):
        """Windows 개발 PC의 과거(2026-10-01) 테스트 계정이 프로덕션 클라우드로 역유입되지 않는지 검증"""
        am._atomic_write_json(self.accounts_json, {
            "testadmin": {
                "username": "testadmin",
                "password": hash_password("oldtest123"),
                "name": "테스트관리자",
                "role": "ADMIN",
                "note": "테스트 계정",
                "created_at": "2026-10-01 16:10:58",
                "updated_at": "2026-10-01 16:21:01"
            }
        })
        with patch.object(am.os, "name", "nt"):
            AuthManager.get_all_accounts(force_reload=True)

        cloud_rows = [
            r for r in self.fake_cloud.store["worktime_hourly_rates"]
            if r.get("hourly_rate") == CLOUD_ACCOUNTS_RATE_SLOT
        ]
        self.assertEqual(len(cloud_rows), 0)

    def test_cookie_session_restore_password_invalidation_and_logout_guard(self):
        """
        1) 로그인 후 브라우저 새로고침 & 컨테이너 재시작(로컬 세션 파일 삭제) 시에도 쿠키 + 클라우드(-99994)로 복원되는지 확인
        2) 비밀번호 변경 시 기존 기기의 세션 쿠키가 즉시 무효화되는지 확인
        3) 계정 삭제 시 Tombstone으로 재부활이 차단되고 세션이 파기되는지 확인
        4) 로그아웃 직후 브라우저에 쿠키가 아직 남아 있어도 좀비 재로그인이 차단되는지 확인
        """
        succ, _ = AuthManager.create_account("kim_admin", "KimPass123!", name="김관리")
        self.assertTrue(succ)

        succ, _ = AuthManager.login_with_status("kim_admin", "KimPass123!")
        self.assertTrue(succ)
        token = st.session_state["auth_user"]["token"]

        # 클라우드 -99994 세션 레코드 생성 확인
        sess_rows = [
            r for r in self.fake_cloud.store["worktime_hourly_rates"]
            if r.get("hourly_rate") == CLOUD_SESSIONS_RATE_SLOT
        ]
        self.assertEqual(len(sess_rows), 1)

        # F5 새로고침 + 컨테이너 재부팅 시뮬레이션 (session_state 및 로컬 .session_cache.json 삭제, 브라우저 쿠키만 보유)
        st.session_state.clear()
        if self.session_json.exists():
            self.session_json.unlink()

        with patch.object(AuthManager, "_get_browser_cookie", return_value=token):
            self.assertTrue(AuthManager.is_authenticated())
            self.assertEqual(AuthManager.get_current_user(), "kim_admin")

            # 로그아웃 직후 브라우저가 아직 쿠키를 못 지운 상태에서도 자동 복원 차단 검증
            AuthManager.logout()
            self.assertFalse(AuthManager.is_authenticated())

        # 다시 로그인 후 다른 관리자가 비밀번호를 변경했을 때 기존 토큰 즉시 무효화 검증
        st.session_state.clear()
        self.assertTrue(AuthManager.login("kim_admin", "KimPass123!"))
        token2 = st.session_state["auth_user"]["token"]
        st.session_state.clear()  # 타 기기 탭 시뮬레이션

        AuthManager.update_account_password("kim_admin", "NewKimPass999!")
        with patch.object(AuthManager, "_get_browser_cookie", return_value=token2):
            self.assertFalse(AuthManager.is_authenticated())

        # 계정 삭제 시 Tombstone 기록으로 재부활 원천 차단 검증
        del_ok, _ = AuthManager.delete_account("kim_admin")
        self.assertTrue(del_ok)
        all_usernames = [a["username"].lower() for a in AuthManager.get_all_accounts(force_reload=True)]
        self.assertNotIn("kim_admin", all_usernames)


if __name__ == "__main__":
    unittest.main()
