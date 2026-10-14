import unittest
import os
import sqlite3
from pathlib import Path
from src.services.cost_vault_service import CostVaultService, VERIFIER_PLAINTEXT

class TestCostVaultService(unittest.TestCase):
    def setUp(self):
        CostVaultService.lock()
        # 임시 테이블 초기화
        CostVaultService._ensure_local_vault_table()

    def tearDown(self):
        CostVaultService.lock()

    def test_derive_key_deterministic(self):
        salt = b"test_salt_16byte"
        k1 = CostVaultService.derive_key("my_secure_pw", salt)
        k2 = CostVaultService.derive_key("my_secure_pw", salt)
        self.assertEqual(k1, k2)
        # 다른 비밀번호는 다른 키 생성
        k3 = CostVaultService.derive_key("different_pw", salt)
        self.assertNotEqual(k1, k3)

    def test_vault_setup_and_unlock(self):
        test_pw = "master_secret_1234!"
        ok, msg = CostVaultService.setup_initial_vault(test_pw)
        self.assertTrue(ok)
        self.assertTrue(CostVaultService.is_unlocked())

        # 암호화 / 복호화 검증
        plain_money = 80000
        enc_money = CostVaultService.encrypt_int(plain_money)
        self.assertTrue(enc_money.startswith("ENC:"))
        self.assertNotEqual(str(plain_money), enc_money)

        # 복호화
        dec_money = CostVaultService.decrypt_int(enc_money)
        self.assertEqual(dec_money, plain_money)

        # 잠금 (Lock)
        CostVaultService.lock()
        self.assertFalse(CostVaultService.is_unlocked())
        # 잠긴 상태에서 복호화 시 fallback (0) 반환
        self.assertEqual(CostVaultService.decrypt_int(enc_money, fallback=0), 0)

        # 잘못된 비밀번호로 언락 시도 -> 실패
        ok_wrong, msg_wrong = CostVaultService.unlock("wrong_password")
        self.assertFalse(ok_wrong)
        self.assertFalse(CostVaultService.is_unlocked())

        # 올바른 비밀번호로 언락 시도 -> 성공
        ok_correct, msg_correct = CostVaultService.unlock(test_pw)
        self.assertTrue(ok_correct)
        self.assertTrue(CostVaultService.is_unlocked())
        self.assertEqual(CostVaultService.decrypt_int(enc_money), plain_money)

    def test_plain_text_backward_compatibility(self):
        # 기존 평문 데이터는 암호문이 아니므로 그대로 통과
        CostVaultService.lock()
        self.assertEqual(CostVaultService.decrypt_int(50000), 50000)
        self.assertEqual(CostVaultService.decrypt_str("일반문자열"), "일반문자열")
        self.assertEqual(CostVaultService.decrypt_float(7.5), 7.5)

if __name__ == "__main__":
    unittest.main()
