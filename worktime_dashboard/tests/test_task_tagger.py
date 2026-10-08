# -*- coding: utf-8 -*-
import unittest
import pandas as pd
from src.services.task_tagger import classify_text, apply_task_tags

class TestTaskTagger(unittest.TestCase):
    def test_classify_aci_inspection(self):
        domain, wtype = classify_text("수협은행 APIC 클러스터 및 Leaf 스위치 정기점검 지원")
        self.assertEqual(domain, "Cisco ACI")
        self.assertEqual(wtype, "정기점검")

    def test_classify_nexus_trouble(self):
        domain, wtype = classify_text("농협 N9K 코어 스위치 링크 단절 긴급 장애 처리")
        self.assertEqual(domain, "Cisco Nexus")
        self.assertEqual(wtype, "장애대응 / 긴급")

    def test_classify_catalyst_upgrade(self):
        domain, wtype = classify_text("BGF 본사 C9300 스위치 IOS 펌웨어 패치 및 업그레이드")
        self.assertEqual(domain, "Catalyst / 스위치")
        self.assertEqual(wtype, "패치 / 업그레이드")

    def test_classify_firewall_config(self):
        domain, wtype = classify_text("대구은행 차세대 방화벽(FTD) 보안 정책 및 NAT 설정 변경")
        self.assertEqual(domain, "보안 / 방화벽")
        self.assertEqual(wtype, "구성변경 / 설정")

    def test_classify_wireless_install(self):
        domain, wtype = classify_text("신세계백화점 신규 매장 무선 AP 및 WLC 컨트롤러 신규 구축 및 설치")
        self.assertEqual(domain, "무선 / AP")
        self.assertEqual(wtype, "신규구축 / 설치")

    def test_classify_router_wan(self):
        domain, wtype = classify_text("지점 BGP 라우터 WAN 전용선 대역폭 테스트 및 기술지원 회의")
        self.assertEqual(domain, "라우터 / WAN")
        self.assertEqual(wtype, "기술지원 / 회의")

    def test_apply_task_tags_dataframe(self):
        sample_df = pd.DataFrame([
            {"task_description": "ACI Spine 점검", "raw_start_message": "", "client_name": "A사"},
            {"task_description": "방화벽 긴급 복구", "raw_start_message": "", "client_name": "B사"},
            {"task_description": "단순 보고서 작성", "raw_start_message": "", "client_name": "C사"},
        ])
        tagged_df = apply_task_tags(sample_df)
        self.assertIn("tech_domain", tagged_df.columns)
        self.assertIn("work_type", tagged_df.columns)
        self.assertEqual(tagged_df.iloc[0]["tech_domain"], "Cisco ACI")
        self.assertEqual(tagged_df.iloc[0]["work_type"], "정기점검")
        self.assertEqual(tagged_df.iloc[1]["tech_domain"], "보안 / 방화벽")
        self.assertEqual(tagged_df.iloc[1]["work_type"], "장애대응 / 긴급")
        self.assertEqual(tagged_df.iloc[2]["tech_domain"], "일반 네트워크")
        self.assertEqual(tagged_df.iloc[2]["work_type"], "일반 업무")

if __name__ == "__main__":
    unittest.main()
