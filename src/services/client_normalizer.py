import re
import pandas as pd
from typing import Optional

# 대표 고객사 정규화 매핑 사전
EXACT_MAPPINGS = {
    # KB 계열
    "kb신용정보": "KB신용정보",
    "kb 신용정보": "KB신용정보",
    "KB 신용정보": "KB신용정보",
    "KB신용정보(주)": "KB신용정보",
    "kb카드": "KB국민카드",
    "KB카드": "KB국민카드",
    "kb증권": "KB증권",
    "KB증권": "KB증권",
    "kb손해보험": "KB손해보험",
    "KB손해보험": "KB손해보험",
    
    # IM뱅크 / DGB대구은행
    "im뱅크": "IM뱅크",
    "iM뱅크": "IM뱅크",
    "i'm뱅크": "IM뱅크",
    "I'm뱅크": "IM뱅크",
    "im 뱅크": "IM뱅크",
    "IM 뱅크": "IM뱅크",
    "iM 뱅크": "IM뱅크",
    "iM뱅크(대구은행)": "IM뱅크",
    "dgb대구은행": "IM뱅크",
    "DGB대구은행": "IM뱅크",
    
    # KDB생명 / 산업은행
    "kdb생명": "KDB생명",
    "kdb 생명": "KDB생명",
    "KDB 생명": "KDB생명",
    "kdb산업은행": "KDB산업은행",
    "KDB 산업은행": "KDB산업은행",
    
    # BGF리테일
    "bgf리테일": "BGF리테일",
    "bgf 리테일": "BGF리테일",
    "BGF 리테일": "BGF리테일",
    "bgf": "BGF리테일",
    "BGF": "BGF리테일",
    
    # AIG손해보험
    "aig손해보험": "AIG손해보험",
    "aig 손해보험": "AIG손해보험",
    "AIG 손해보험": "AIG손해보험",
    "aig손보": "AIG손해보험",
    "AIG손보": "AIG손해보험",
    "aig": "AIG손해보험",
    "AIG": "AIG손해보험",
    
    # NHN KCP
    "nhnkcp": "NHNKCP",
    "nhn kcp": "NHNKCP",
    "NHN KCP": "NHNKCP",
    "NHN-KCP": "NHNKCP",
    "NHN KCP(주)": "NHNKCP",
    
    # 벤더사 / IT 솔루션
    "cisco": "Cisco",
    "CISCO": "Cisco",
    "dell": "Dell",
    "DELL": "Dell",
    "arista": "Arista",
    "ARISTA": "Arista",
    "아리스타": "Arista",
    "hpe": "HPE",
    "HPE(주)": "HPE",
    "skb": "SKB",
    "SK브로드밴드": "SKB",
    "akis": "AKIS",
    "AKIS(주)": "AKIS",
    "bkr": "BKR",
    "BKR(버거킹)": "BKR",
    
    # 금융권
    "ibk기업은행": "IBK기업은행",
    "ibk 기업은행": "IBK기업은행",
    "IBK 기업은행": "IBK기업은행",
    "ibk": "IBK기업은행",
    "IBK": "IBK기업은행",
    "sbi저축은행": "SBI저축은행",
    "SBI 저축은행": "SBI저축은행",
    "sbi": "SBI저축은행",
    "SBI": "SBI저축은행",
    "sh수협은행": "수협은행",
    "SH수협은행": "수협은행",
    "sh 수협은행": "수협은행",
    "SH 수협은행": "수협은행",
    "SH 은행": "수협은행",
    "sh 은행": "수협은행",
}

def normalize_client_name(name: Optional[str]) -> str:
    """
    고객사명을 대소문자, 띄어쓰기 차이 없이 표준 대표 명칭으로 정규화합니다.
    예: 'kb신용정보', 'KB 신용정보' -> 'KB신용정보'
    """
    if not name or pd.isna(name):
        return ""
    
    cleaned = str(name).strip()
    if not cleaned:
        return ""
        
    lower_cleaned = cleaned.lower()
    
    # 1. 사전 매핑 일치 확인
    if lower_cleaned in EXACT_MAPPINGS:
        return EXACT_MAPPINGS[lower_cleaned]
    if cleaned in EXACT_MAPPINGS:
        return EXACT_MAPPINGS[cleaned]
        
    # 2. 영문 시작 대문자화 (예: kb신용정보 -> KB신용정보, lg유플러스 -> LG유플러스)
    m = re.match(r"^([a-zA-Z]+)(.*)$", cleaned)
    if m:
        eng_part = m.group(1).upper()
        rest_part = m.group(2).strip()
        
        # 특정 브랜드는 첫 글자만 대문자 (Title case)
        if eng_part.lower() in ["cisco", "dell", "arista", "ruckus", "verkada", "splunk", "fortinet"]:
            eng_part = eng_part.capitalize()
            
        return f"{eng_part}{rest_part}"
        
    return cleaned
