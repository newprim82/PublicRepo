import re
import functools
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
    
    # 벤더사 / IT 솔루션 (한글 / 영문 통합 정규화)
    "cisco": "Cisco",
    "CISCO": "Cisco",
    "시스코": "Cisco",
    "dell": "Dell",
    "DELL": "Dell",
    "델": "Dell",
    "arista": "Arista",
    "ARISTA": "Arista",
    "아리스타": "Arista",
    "juniper": "Juniper",
    "JUNIPER": "Juniper",
    "주니퍼": "Juniper",
    "fortinet": "Fortinet",
    "FORTINET": "Fortinet",
    "포티넷": "Fortinet",
    "paloalto": "Palo Alto",
    "PALOALTO": "Palo Alto",
    "palo alto": "Palo Alto",
    "팔로알토": "Palo Alto",
    "checkpoint": "Check Point",
    "CHECKPOINT": "Check Point",
    "check point": "Check Point",
    "체크포인트": "Check Point",
    "f5": "F5",
    "F5": "F5",
    "에프파이브": "F5",
    "netapp": "NetApp",
    "NETAPP": "NetApp",
    "넷앱": "NetApp",
    "lenovo": "Lenovo",
    "LENOVO": "Lenovo",
    "레노버": "Lenovo",
    "hpe": "HPE",
    "HPE": "HPE",
    "HPE(주)": "HPE",
    "에이치피이": "HPE",
    "hp": "HPE",
    "HP": "HPE",
    "skb": "SKB",
    "SKB": "SKB",
    "SK브로드밴드": "SKB",
    "akis": "AKIS",
    "AKIS": "AKIS",
    "AKIS(주)": "AKIS",
    "bkr": "BKR",
    "BKR": "BKR",
    "BKR(버거킹)": "BKR",
    "버거킹": "BKR",
    "ruckus": "Ruckus",
    "루커스": "Ruckus",
    "splunk": "Splunk",
    "스플렁크": "Splunk",
    "verkada": "Verkada",
    "버카다": "Verkada",
    "vmware": "VMware",
    "VMware": "VMware",
    "브이엠웨어": "VMware",
    "veeam": "Veeam",
    "빔소프트웨어": "Veeam",
    "oracle": "Oracle",
    "오라클": "Oracle",
    "microsoft": "Microsoft",
    "마이크로소프트": "Microsoft",
    "aws": "AWS",
    "아마존": "AWS",
    "gcp": "GCP",
    "구글": "GCP",
    
    # 금융권
    "ibk기업은행": "IBK기업은행",
    "ibk 기업은행": "IBK기업은행",
    "IBK 기업은행": "IBK기업은행",
    "ibk": "IBK기업은행",
    "IBK": "IBK기업은행",
    "기업은행": "IBK기업은행",
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
    "수협": "수협은행",
}

# 접두사 기반 지점/복합명 정규화 룰 (예: 'iM뱅크 부산영업부' -> 'IM뱅크 부산영업부')
PREFIX_RULES = [
    (re.compile(r"^(?i:im|i'm)\s*뱅크", re.IGNORECASE), "IM뱅크"),
    (re.compile(r"^(?i:nhn)\s*[-_]?\s*kcp", re.IGNORECASE), "NHNKCP"),
    (re.compile(r"^(?i:kdb)\s*생명", re.IGNORECASE), "KDB생명"),
    (re.compile(r"^(?i:kdb)\s*산업은행", re.IGNORECASE), "KDB산업은행"),
    (re.compile(r"^(?i:kb)\s*신용정보", re.IGNORECASE), "KB신용정보"),
    (re.compile(r"^(?i:kb)\s*국민카드|^(?i:kb)\s*카드", re.IGNORECASE), "KB국민카드"),
    (re.compile(r"^(?i:kb)\s*손해보험", re.IGNORECASE), "KB손해보험"),
    (re.compile(r"^(?i:kb)\s*증권", re.IGNORECASE), "KB증권"),
    (re.compile(r"^(?i:bgf)\s*리테일", re.IGNORECASE), "BGF리테일"),
    (re.compile(r"^(?i:aig)\s*손해보험|^(?i:aig)\s*손보", re.IGNORECASE), "AIG손해보험"),
    (re.compile(r"^(?i:ibk)\s*기업은행", re.IGNORECASE), "IBK기업은행"),
    (re.compile(r"^(?i:sbi)\s*저축은행", re.IGNORECASE), "SBI저축은행"),
    (re.compile(r"^(?i:sh)\s*수협은행|^(?i:sh)\s*은행", re.IGNORECASE), "수협은행"),
    (re.compile(r"^(?i:arista|아리스타)", re.IGNORECASE), "Arista"),
    (re.compile(r"^(?i:cisco|시스코)", re.IGNORECASE), "Cisco"),
    (re.compile(r"^(?i:dell|델)", re.IGNORECASE), "Dell"),
    (re.compile(r"^(?i:juniper|주니퍼)", re.IGNORECASE), "Juniper"),
    (re.compile(r"^(?i:fortinet|포티넷)", re.IGNORECASE), "Fortinet"),
]

@functools.lru_cache(maxsize=2048)
def normalize_client_name(name: Optional[str]) -> str:
    """
    고객사명을 한글/영문, 대소문자, 띄어쓰기 차이 없이 표준 대표 명칭으로 정규화합니다.
    예:
      - '아리스타', 'arista', 'ARISTA' -> 'Arista'
      - '시스코', 'cisco', 'CISCO' -> 'Cisco'
      - 'iM뱅크 부산영업부', 'im 뱅크' -> 'IM뱅크 부산영업부', 'IM뱅크'
      - 'nhnkcp', 'NHN KCP' -> 'NHNKCP'
      - 'kdb 생명' -> 'KDB생명'
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
        
    # 2. 접두사 규칙 적용 (지점명 등이 결합된 복합 고객사명 정규화)
    for pattern, std_prefix in PREFIX_RULES:
        if pattern.match(cleaned):
            remainder = pattern.sub("", cleaned).strip()
            return f"{std_prefix} {remainder}".strip() if remainder else std_prefix

    # 3. 영문 시작 대문자화 (예: lg유플러스 -> LG유플러스)
    m = re.match(r"^([a-zA-Z]+)(.*)$", cleaned)
    if m:
        eng_part = m.group(1).upper()
        rest_part = m.group(2).strip()
        
        # 특정 브랜드는 첫 글자만 대문자 (Title case)
        if eng_part.lower() in ["cisco", "dell", "arista", "ruckus", "verkada", "splunk", "fortinet", "juniper"]:
            eng_part = eng_part.capitalize()
            
        return f"{eng_part}{rest_part}"
        
    return cleaned


COMPOUND_OUTLOOK_CLIENT_PATTERNS = [
    (re.compile(r"^(?:대구\s*)?(?:i\'?m|im)\s*뱅크(?:\s*\(대구은행\))?", re.IGNORECASE), "IM뱅크"),
    (re.compile(r"^dgb\s*대구은행", re.IGNORECASE), "IM뱅크"),
    (re.compile(r"^kb\s*(?:신용정보|국민카드|카드|증권|손해보험|국민은행|은행)", re.IGNORECASE), lambda m: normalize_client_name(m.group(0))),
    (re.compile(r"^kdb\s*(?:생명|산업은행)", re.IGNORECASE), lambda m: normalize_client_name(m.group(0))),
    (re.compile(r"^ibk\s*기업은행", re.IGNORECASE), "IBK기업은행"),
    (re.compile(r"^sbi\s*저축은행", re.IGNORECASE), "SBI저축은행"),
    (re.compile(r"^sh\s*(?:수협은행|수협|은행)", re.IGNORECASE), "수협은행"),
    (re.compile(r"^bgf\s*리테일", re.IGNORECASE), "BGF리테일"),
    (re.compile(r"^nhn\s*kcp", re.IGNORECASE), "NHNKCP"),
    (re.compile(r"^aig\s*(?:손해보험|손보)", re.IGNORECASE), "AIG손해보험"),
    (re.compile(r"^상상인\s*플러스(?:\s*저축은행)?", re.IGNORECASE), "상상인플러스저축은행"),
    (re.compile(r"^한국투자\s*저축은행", re.IGNORECASE), "한국투자저축은행"),
    (re.compile(r"^하나\s*(?:은행|카드|대체투자자산운용|금융)", re.IGNORECASE), lambda m: normalize_client_name(m.group(0))),
]

def parse_outlook_subject_to_client_and_task(subject: str, location: str = "") -> Tuple[str, str]:
    """
    아웃룩 일정 제목에서 [작업자] 태그를 제거하고,
    고객사명(client_name)과 작업 내용(task_description)을 지능적으로 분리 파싱합니다.
    예:
      - '[이동우] IM뱅크 통신사 사용자 고도화 구축 프로젝트' -> ('IM뱅크', '통신사 사용자 고도화 구축 프로젝트')
      - '[김경현] 대구 iM 뱅크 지원' -> ('IM뱅크', '지원')
      - '[김경현] 하나카드 고객사 신입기본교육' -> ('하나카드', '고객사 신입기본교육')
    """
    raw_subj = str(subject or "").strip()
    if not raw_subj:
        return "기타", "아웃룩 일정"
        
    # 1. 선행 대괄호 [이름] 또는 [태그] 추출 및 제거
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", raw_subj).strip()
    if not cleaned:
        tag = re.search(r"\[([^\]]+)\]", raw_subj)
        return "기타", tag.group(1) if tag else raw_subj

    # 사내/회의 예외 처리
    if any(k in cleaned for k in ["기술 미팅", "업무회의", "팀별 회의", "본부 회의", "주간 회의"]):
        return "내부업무", cleaned

    # 2. 알려진 복합 고객사 패턴 우선 매칭
    matched_client = None
    task_desc = cleaned

    for pat, repl in COMPOUND_OUTLOOK_CLIENT_PATTERNS:
        m = pat.match(cleaned)
        if m:
            c_name = repl(m) if callable(repl) else repl
            matched_client = c_name
            task_desc = cleaned[m.end():].strip()
            break

    # 3. 구분자(-, :, /) 또는 첫 단어 기준 분리
    if not matched_client:
        if " - " in cleaned:
            parts = cleaned.split(" - ", 1)
            matched_client = normalize_client_name(parts[0].strip())
            task_desc = parts[1].strip()
        elif " : " in cleaned or ":" in cleaned:
            parts = re.split(r"\s*:\s*", cleaned, 1)
            matched_client = normalize_client_name(parts[0].strip())
            task_desc = parts[1].strip()
        else:
            words = cleaned.split(maxsplit=1)
            first_w = words[0]
            norm_first = normalize_client_name(first_w)
            matched_client = norm_first
            task_desc = words[1].strip() if len(words) > 1 else cleaned

    if not task_desc:
        task_desc = cleaned

    if not matched_client or len(matched_client) < 2:
        loc = str(location or "").strip()
        if loc and "Teams" not in loc and "Zoom" not in loc and len(loc) >= 2:
            matched_client = normalize_client_name(loc)
        else:
            matched_client = "기타"

    return matched_client, task_desc
