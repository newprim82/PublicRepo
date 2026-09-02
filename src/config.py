import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 경로
BASE_DIR = Path(__file__).resolve().parent.parent

# .env 파일 로드
load_dotenv(BASE_DIR / ".env")

# 프로젝트 공용 Supabase 클라우드 기본 접속 정보 (어떤 PC에서든 .env 없이도 즉시 자동 동기화)
DEFAULT_SUPABASE_URL = "https://dzjvpagehccyluqrjyiq.supabase.co"
DEFAULT_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR6anZwYWdlaGNjeWx1cXJqeWlxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODU0MzA3MDUsImV4cCI6MjEwMTAwNjcwNX0.WXaCftnKX2hKfPCvybmXMddUPoODhxXURU0kUVoLeVQ"

class Config:
    # Supabase 클라우드 DB 설정 (.env 설정값 우선, 없으면 기본 공용 접속 정보 자동 사용)
    SUPABASE_URL: str = (os.getenv("SUPABASE_URL", "").strip() or DEFAULT_SUPABASE_URL)
    SUPABASE_KEY: str = (os.getenv("SUPABASE_KEY", "").strip() or DEFAULT_SUPABASE_KEY)

    # Streamlit Cloud 배포 URL (24시간 Keep-Alive 슬립 방지용)
    STREAMLIT_APP_URL: str = os.getenv("STREAMLIT_APP_URL", "").strip()

    # 카카오톡 연동 설정 (디버깅용 1분 = 60초)
    KAKAO_CHAT_TITLE: str = os.getenv("KAKAO_CHAT_TITLE", "[기술본부] 업무공유방").strip()
    COLLECTOR_INTERVAL_SECONDS: int = 60
    
    # 로컬 SQLite 데이터베이스 경로
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
