# -*- coding: utf-8 -*-
"""
📝 기술본부 관제 포털 표준 로깅 모듈 (Single Source of Truth)
- 콘솔 및 data/app.log 파일 동시 기록
- 구조화된 로그 포맷 제공
"""

import logging
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "data"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

_LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 루트 핸들러 설정 (중복 방지)
_configured = False


def setup_root_logger():
    global _configured
    if _configured:
        return
    _configured = True

    root_logger = logging.getLogger("worktime")
    root_logger.setLevel(logging.INFO)

    # 1. 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root_logger.addHandler(console_handler)

    # 2. 파일 핸들러 (최대 10MB)
    try:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        root_logger.addHandler(file_handler)
    except Exception:
        pass


def get_logger(name: str) -> logging.Logger:
    """모듈별 서브 로거 반환"""
    setup_root_logger()
    return logging.getLogger(f"worktime.{name}")
