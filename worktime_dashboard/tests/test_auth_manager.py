# -*- coding: utf-8 -*-
import unittest
from src.auth.auth_manager import (
    hash_password,
    verify_password,
    is_hashed_password,
    AuthManager
)


class TestAuthSecurity(unittest.TestCase):
    """관리자 인증 및 비밀번호 해시, 무차별 대입 방어 단위 테스트"""

    def setUp(self):
        AuthManager._failed_attempts.clear()

    def test_password_hash_and_verify(self):
        pwd = "SecretPassword123!"
        hashed = hash_password(pwd)
        
        self.assertTrue(is_hashed_password(hashed))
        self.assertTrue(verify_password(pwd, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

    def test_brute_force_lockout(self):
        test_user = "test_attacker"
        
        # 4회 실패 시에는 잠금되지 않음
        for i in range(4):
            count, rem = AuthManager.record_failed_attempt(test_user)
            self.assertEqual(count, i + 1)
            self.assertFalse(AuthManager.is_account_locked(test_user)[0])

        # 5회 실패 시 3분 잠금 활성화
        count, rem = AuthManager.record_failed_attempt(test_user)
        self.assertEqual(count, 5)
        self.assertEqual(rem, 0)
        
        is_locked, remaining_sec = AuthManager.is_account_locked(test_user)
        self.assertTrue(is_locked)
        self.assertGreater(remaining_sec, 0)

        # 리셋 시 잠금 해제
        AuthManager.reset_failed_attempts(test_user)
        self.assertFalse(AuthManager.is_account_locked(test_user)[0])


if __name__ == "__main__":
    unittest.main()
