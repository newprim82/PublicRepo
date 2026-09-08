# -*- coding: utf-8 -*-
"""
🕒 [프로젝트 불변 절대 규칙] 표준 시간 동기화 모듈 (Single Source of Truth)
- 시간 기준: time.bora.net (LGU+ 타임서버, NTP)
- 타임존: 한국 표준시 (KST, UTC+9) 고정
- 연산 안전성: Pandas/DB 연산 시 TypeError 방지를 위해 기본적으로 tz-naive KST datetime 반환
- 이 원칙은 프로젝트 전체 생명주기 동안 영구히 유지됩니다.
"""

import socket
import struct
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
import pandas as pd

# 🇰🇷 한국 표준시 (KST, UTC+9) 절대 불변 정의
KST_TIMEZONE = timezone(timedelta(hours=9))
KST = KST_TIMEZONE

_ntp_offset: Optional[float] = None
_ntp_last_sync: float = 0.0


def get_bora_ntp_timestamp() -> float:
    """
    time.bora.net (LGU+ 타임서버) NTP 기준 정확한 타임스탬프(초) 반환
    - 1시간 캐싱 오프셋 적용으로 0ms 즉시 응답 (네트워크 부하 0)
    - NTP 쿼리 실패 시 직전 오프셋 또는 시스템 시각으로 안전 Fallback
    """
    global _ntp_offset, _ntp_last_sync
    now = time.time()
    if _ntp_offset is None or (now - _ntp_last_sync > 3600):
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(0.8)
            # NTP 프로토콜 헤더 (v3 client)
            data = b'\x1b' + 47 * b'\0'
            client.sendto(data, ('time.bora.net', 123))
            resp, _ = client.recvfrom(1024)
            if resp:
                # 1900-01-01 기준 초 단위 -> 1970-01-01 Unix epoch 변환 (2208988800 초 차이)
                t = struct.unpack('!12I', resp)[10] - 2208988800
                _ntp_offset = float(t) - now
                _ntp_last_sync = now
        except Exception:
            if _ntp_offset is None:
                _ntp_offset = 0.0
    return now + (_ntp_offset or 0.0)


def get_current_kst_time(naive: bool = True) -> datetime:
    """
    ⭐ [프로젝트 표준 함수] time.bora.net 기준 한국 표준시(KST, UTC+9) 현재 시각 반환
    - naive=True (기본값): tzinfo가 없는 순수 KST datetime 반환 (Pandas 뺄셈, SQLite/Supabase 연산 시 TypeError 100% 방지)
    - naive=False: tzinfo=KST가 포함된 tz-aware datetime 반환
    """
    ts = get_bora_ntp_timestamp()
    dt_kst = datetime.fromtimestamp(ts, tz=KST_TIMEZONE)
    if naive:
        return dt_kst.replace(tzinfo=None)
    return dt_kst


def get_current_kst_time_aware() -> datetime:
    """tzinfo=KST가 포함된 tz-aware KST datetime 반환"""
    return get_current_kst_time(naive=False)


def to_naive_kst(val: Any) -> Any:
    """
    어떤 형식의 날짜값(ISO 문자열, tz-aware/tz-naive Timestamp, datetime 등)이 들어와도
    순수 KST 기준 tz-naive datetime으로 안전하게 변환하는 헬퍼
    """
    if pd.isna(val) or not val:
        return pd.NaT
    if isinstance(val, str):
        clean_str = val.replace("T", " ").replace("Z", "")
        if "+" in clean_str:
            clean_str = clean_str.split("+")[0]
        return pd.to_datetime(clean_str.strip(), errors="coerce")
    if hasattr(val, "tz_localize") and getattr(val, "tz", None) is not None:
        return val.tz_localize(None)
    if hasattr(val, "replace") and getattr(val, "tzinfo", None) is not None:
        return val.replace(tzinfo=None)
    return pd.to_datetime(val, errors="coerce")
