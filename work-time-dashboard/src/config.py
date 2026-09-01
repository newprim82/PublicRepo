import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 경로
BASE_DIR = Path(__file__).resolve().parent.parent

# .env 파일 로드
load_dotenv(BASE_DIR / ".env")

class Config:
    # 카카오톡 연동 설정
    KAKAO_CHAT_TITLE: str = os.getenv("KAKAO_CHAT_TITLE", "[기술본부] 업무공유방").strip()
    COLLECTOR_INTERVAL_SECONDS: int = int(os.getenv("COLLECTOR_INTERVAL_SECONDS", "3600"))
    
    # 로컬 SQLite 데이터베이스 경로
    LOCAL_DB_PATH: Path = BASE_DIR / os.getenv("LOCAL_DB_PATH", "data/worklog.db")
    SAMPLE_DATA_DIR: Path = BASE_DIR / "sample_data"

config = Config()
