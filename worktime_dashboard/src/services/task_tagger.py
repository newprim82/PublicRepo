# -*- coding: utf-8 -*-
"""
🏷️ 기술 장비군 & 작업 유형 지능형 룰 기반 태거 (Task Tagger)
- 카카오톡 시작 메시지 및 작업 내용(task_description)을 분석하여
  1) 기술/장비 도메인 (Tech Domain)
  2) 작업 유형 (Work Type)
  을 자동으로 추출하고 정규화합니다.
"""

import re
from typing import Tuple
import pandas as pd

# ==============================================================================
# 1. 기술 / 장비 도메인 키워드 규칙 (우선순위 순서대로 매칭)
# ==============================================================================
TECH_DOMAIN_RULES = [
    # Cisco ACI
    (
        "Cisco ACI",
        [r"\baci\b", r"\bapic\b", r"\bspine\b", r"\bleaf\b", r"스파인", r"리프", r"넥서스\s*9k\s*aci"]
    ),
    # Cisco Nexus (ACI 제외 일반 NX-OS/Nexus)
    (
        "Cisco Nexus",
        [r"\bnexus\b", r"\bn9k\b", r"\bn7k\b", r"\bn5k\b", r"\bn3k\b", r"넥서스"]
    ),
    # Catalyst 및 스위치
    (
        "Catalyst / 스위치",
        [
            r"\bcatalyst\b", r"\bc9\d{3}\b", r"\bc3\d{3}\b", r"\bc2\d{3}\b",
            r"카탈리스트", r"스위치", r"\bl2\b", r"\bl3\b", r"\bl4\b", r"\bl7\b",
            r"백본", r"backbone", r"워크그룹", r"wg\s*sw"
        ]
    ),
    # 보안 및 방화벽
    (
        "보안 / 방화벽",
        [
            r"방화벽", r"firewall", r"\basa\b", r"\bftd\b", r"\bfmc\b",
            r"fortinet", r"포티넷", r"paloalto", r"팔로알토", r"시큐아이",
            r"\bips\b", r"\bids\b", r"\bvpn\b", r"vpn장비"
        ]
    ),
    # 무선 및 AP
    (
        "무선 / AP",
        [r"\bap\b", r"무선", r"\bwlc\b", r"컨트롤러", r"와이파이", r"wifi", r"aironet"]
    ),
    # 라우터 및 WAN
    (
        "라우터 / WAN",
        [r"라우터", r"router", r"\bwan\b", r"\bbgp\b", r"\bospf\b", r"회선", r"전용선"]
    ),
    # 서버 및 가상화
    (
        "서버 / 가상화",
        [r"서버", r"server", r"vmware", r"esxi", r"hyper-v", r"\bucs\b", r"nutanix", r"뉴타닉스", r"호스트"]
    ),
]

DEFAULT_TECH_DOMAIN = "일반 네트워크"


# ==============================================================================
# 2. 작업 유형 키워드 규칙 (우선순위 순서대로 매칭)
# ==============================================================================
WORK_TYPE_RULES = [
    # 정기점검
    (
        "정기점검",
        [
            r"정기점검", r"정점", r"예방점검", r"월간점검", r"분기점검",
            r"반기점검", r"연간점검", r"체크리스트", r"inspection", r"health\s*check",
            r"정기\s*순회", r"상태점검", r"일일점검", r"점검"
        ]
    ),
    # 장애대응 및 긴급
    (
        "장애대응 / 긴급",
        [
            r"장애", r"긴급", r"emergency", r"trouble", r"오류", r"다운",
            r"먹통", r"단절", r"복구", r"트러블", r"에러", r"failover", r"페일오버"
        ]
    ),
    # 패치 및 업그레이드
    (
        "패치 / 업그레이드",
        [
            r"패치", r"업그레이드", r"upgrade", r"patch", r"펌웨어",
            r"\bios\b", r"버전", r"릴리즈", r"firmware"
        ]
    ),
    # 신규구축 및 설치
    (
        "신규구축 / 설치",
        [
            r"구축", r"설치", r"install", r"setup", r"마이그레이션",
            r"교체", r"컷오버", r"이전", r"신규", r"deploy", r"배포"
        ]
    ),
    # 구성변경 및 설정
    (
        "구성변경 / 설정",
        [
            r"설정", r"config", r"변경", r"등록", r"추가",
            r"삭제", r"수정", r"정책", r"policy", r"vlan", r"\bip\b"
        ]
    ),
    # 상주 지원
    (
        "상주 지원",
        [
            r"상주지원", r"상주\s*근무", r"상주\s*작업", r"상주\s*엔지니어",
            r"상주\s*인력", r"상주", r"resident"
        ]
    ),
    # 회의 / 협의
    (
        "회의 / 협의",
        [
            r"회의", r"미팅", r"협의", r"세미나", r"교육",
            r"meeting", r"seminar", r"보고회", r"컨퍼런스"
        ]
    ),
    # 기술지원
    (
        "기술지원",
        [
            r"기술지원", r"현장지원", r"원격지원", r"방문지원", r"지원",
            r"검토", r"테스트", r"poc", r"bmt", r"support"
        ]
    ),
]

DEFAULT_WORK_TYPE = "일반 업무"


def classify_text(text: str) -> Tuple[str, str]:
    """
    텍스트를 분석하여 (기술도메인, 작업유형)을 반환합니다.
    """
    if not text or not isinstance(text, str):
        return DEFAULT_TECH_DOMAIN, DEFAULT_WORK_TYPE

    lower_text = text.lower()

    # 1. 기술 / 장비 도메인 분류
    detected_domain = DEFAULT_TECH_DOMAIN
    for domain_name, patterns in TECH_DOMAIN_RULES:
        if any(re.search(pat, lower_text) for pat in patterns):
            detected_domain = domain_name
            break

    # 2. 작업 유형 분류
    detected_type = DEFAULT_WORK_TYPE
    for type_name, patterns in WORK_TYPE_RULES:
        if any(re.search(pat, lower_text) for pat in patterns):
            detected_type = type_name
            break

    return detected_domain, detected_type


def apply_task_tags(df: pd.DataFrame) -> pd.DataFrame:
    """
    데이터프레임의 task_description 및 raw_start_message를 기반으로
    tech_domain, work_type 컬럼을 자동 부여합니다.
    """
    if df is None or df.empty:
        if df is not None:
            if "tech_domain" not in df.columns:
                df["tech_domain"] = ""
            if "work_type" not in df.columns:
                df["work_type"] = ""
        return df

    res_df = df.copy()

    # 텍스트 결합 (task_description + raw_start_message)
    desc_series = res_df.get("task_description", pd.Series("", index=res_df.index)).fillna("").astype(str)
    raw_series = res_df.get("raw_start_message", pd.Series("", index=res_df.index)).fillna("").astype(str)
    client_series = res_df.get("client_name", pd.Series("", index=res_df.index)).fillna("").astype(str)
    
    combined_text = desc_series + " " + raw_series + " " + client_series

    # 벡터화 연산 대신 안전하고 빠른 map/apply
    tags = [classify_text(t) for t in combined_text]
    res_df["tech_domain"] = [t[0] for t in tags]
    res_df["work_type"] = [t[1] for t in tags]

    return res_df
