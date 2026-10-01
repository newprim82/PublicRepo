# -*- coding: utf-8 -*-
import os
import json
from pathlib import Path
from typing import List, Union, Set
from ..config import config

# 프로젝트 루트 및 저장 경로
DATA_DIR = config.BASE_DIR / "data"
AUTH_RECIPIENTS_FILE = DATA_DIR / "authorized_recipients.json"

# 시스템 기본 등록 수신자
DEFAULT_AUTHORIZED_EMAILS = [
    "ymmoon@sangsanginworld.co.kr",
    "newprim82@gmail.com"
]


class AuthorizedRecipientService:
    """
    비용산정 데이터 발송 권한을 가진 사전 등록 수신자(화이트리스트) 관리 서비스
    - 민감한 예상 청구 금액 및 단가 정보는 오직 등록된 메일로만 발송 허용
    - 로컬 JSON 영구 보존 + 환경변수 동적 병합
    """

    @classmethod
    def _ensure_storage(cls) -> Set[str]:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        recipients = set(m.lower().strip() for m in DEFAULT_AUTHORIZED_EMAILS)

        # 환경변수 REPORT_RECIPIENT_EMAILS 병합
        env_recipients = os.getenv("REPORT_RECIPIENT_EMAILS", "")
        if env_recipients:
            for em in env_recipients.split(","):
                clean = em.lower().strip()
                if clean:
                    recipients.add(clean)

        # 정기 메일 발송 대상(EmailScheduleService) 등록 수신자 자동 병합
        try:
            from .email_schedule_service import EmailScheduleService
            sched_recipients = EmailScheduleService.get_all_recipients()
            for sr in sched_recipients:
                if sr.get("include_cost", True):
                    em = str(sr.get("email", "")).lower().strip()
                    if em:
                        recipients.add(em)
        except Exception:
            pass

        return recipients

    @classmethod
    def _save_to_file(cls, recipients: Set[str]):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(AUTH_RECIPIENTS_FILE, "w", encoding="utf-8") as f:
                json.dump(sorted(list(recipients)), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @classmethod
    def get_authorized_recipients(cls) -> List[str]:
        """현재 등록된 승인 수신자 목록 반환 (알파벳순 정렬)"""
        return sorted(list(cls._ensure_storage()))

    @classmethod
    def add_authorized_recipient(cls, email: str) -> bool:
        """새로운 수신자 이메일 등록"""
        clean = str(email).lower().strip()
        if not clean or "@" not in clean:
            return False
        recipients = cls._ensure_storage()
        recipients.add(clean)
        cls._save_to_file(recipients)
        return True

    @classmethod
    def remove_authorized_recipient(cls, email: str) -> bool:
        """등록된 수신자 이메일 삭제 (기본 시스템 메일은 삭제 불가)"""
        clean = str(email).lower().strip()
        if clean in [m.lower() for m in DEFAULT_AUTHORIZED_EMAILS]:
            return False
        recipients = cls._ensure_storage()
        if clean in recipients:
            recipients.remove(clean)
            cls._save_to_file(recipients)
            return True
        return False

    @classmethod
    def parse_recipient_list(cls, recipients: Union[str, List[str]]) -> List[str]:
        """문자열 또는 리스트 형태의 수신자를 정제된 리스트로 변환"""
        if not recipients:
            return []
        if isinstance(recipients, str):
            parts = [r.lower().strip() for r in recipients.split(",") if r.strip()]
        else:
            parts = [str(r).lower().strip() for r in recipients if str(r).strip()]
        return parts

    @classmethod
    def is_all_authorized(cls, recipients: Union[str, List[str]]) -> bool:
        """
        입력된 모든 수신자가 사전에 등록된 이메일인지 철저히 검증.
        단 하나라도 등록되지 않은 메일이 포함되어 있으면 False 반환.
        """
        parsed = cls.parse_recipient_list(recipients)
        if not parsed:
            return False
        auth_set = cls._ensure_storage()
        return all(em in auth_set for em in parsed)

    @classmethod
    def get_unauthorized_recipients(cls, recipients: Union[str, List[str]]) -> List[str]:
        """등록되지 않은 미승인 수신자 목록 반환 (UI 경고용)"""
        parsed = cls.parse_recipient_list(recipients)
        auth_set = cls._ensure_storage()
        return [em for em in parsed if em not in auth_set]
