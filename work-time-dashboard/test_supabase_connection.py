import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.config import config
from supabase import create_client

print(f"SUPABASE_URL: {config.SUPABASE_URL}")
print(f"is_supabase_configured: {config.is_supabase_configured()}")

supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

try:
    res = supabase.table("work_logs").select("id").limit(1).execute()
    print("[성공] Supabase work_logs 테이블에 성공적으로 접근했습니다!")
    print(f"응답 데이터: {res.data}")
except Exception as e:
    print(f"[알림] work_logs 테이블 조회 예외: {e}")
    print("테이블이 아직 생성되지 않았을 수 있습니다. DDL 쿼리 실행이 필요할 수 있습니다.")
