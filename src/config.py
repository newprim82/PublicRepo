import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 경로
BASE_DIR = Path(__file__).resolve().parent.parent

# .env 파일 로드
load_dotenv(BASE_DIR / ".env")

class Config:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip()
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "").strip()
    
    KAKAO_CHAT_TITLE: str = os.getenv("KAKAO_CHAT_TITLE", "기술 1팀").strip()
    COLLECTOR_INTERVAL_SECONDS: int = int(os.getenv("COLLECTOR_INTERVAL_SECONDS", "600"))
    
    LOCAL_DB_PATH: Path = BASE_DIR / os.getenv("LOCAL_DB_PATH", "data/worklog.db")
    SAMPLE_DATA_DIR: Path = BASE_DIR / "sample_data"
    
    @classmethod
    def is_supabase_configured(cls) -> bool:
        return bool(
            cls.SUPABASE_URL 
            and cls.SUPABASE_KEY 
            and "your-project" not in cls.SUPABASE_URL
            and "your-anon" not in cls.SUPABASE_KEY
        )

config = Config()
