# -*- coding: utf-8 -*-
import unittest
from src.services.client_normalizer import normalize_client_name


class TestClientNormalizer(unittest.TestCase):
    """고객사명 정규화 및 표준화 단위 테스트"""

    def test_kb_group(self):
        self.assertEqual(normalize_client_name("kb신용정보"), "KB신용정보")
        self.assertEqual(normalize_client_name("KB 신용정보"), "KB신용정보")
        self.assertEqual(normalize_client_name("KB신용정보(주)"), "KB신용정보")
        self.assertEqual(normalize_client_name("kb카드"), "KB국민카드")
        self.assertEqual(normalize_client_name("kb증권"), "KB증권")

    def test_imbank_group(self):
        self.assertEqual(normalize_client_name("im뱅크"), "IM뱅크")
        self.assertEqual(normalize_client_name("iM뱅크"), "IM뱅크")
        self.assertEqual(normalize_client_name("dgb대구은행"), "IM뱅크")
        self.assertEqual(normalize_client_name("DGB대구은행"), "IM뱅크")
        self.assertEqual(normalize_client_name("대구은행"), "IM뱅크")

    def test_insurance_and_retail(self):
        self.assertEqual(normalize_client_name("aig"), "AIG손해보험")
        self.assertEqual(normalize_client_name("aig손보"), "AIG손해보험")
        self.assertEqual(normalize_client_name("bgf"), "BGF리테일")
        self.assertEqual(normalize_client_name("bgf리테일"), "BGF리테일")

    def test_empty_and_unknown(self):
        self.assertEqual(normalize_client_name(""), "")
        self.assertEqual(normalize_client_name(None), "")
        self.assertEqual(normalize_client_name("알수없는새로운고객사"), "알수없는새로운고객사")


if __name__ == "__main__":
    unittest.main()
