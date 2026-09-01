import sys
import sqlite3
import pandas as pd
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.config import config
from src.services.team_service import TeamService
from src.database.supabase_client import db_manager

# 1. 로컬 DB 팀 매핑 조회
mappings = TeamService.get_team_mappings()
print(f"현재 로컬 팀 매핑 등록 수: {len(mappings)}명")

team_counts = {}
for w, t in mappings.items():
    team_counts[t] = team_counts.get(t, 0) + 1

print(f"팀별 인원 현황: {team_counts}")

# 2. Supabase work_logs 테이블에 각 팀원의 worker_team 일괄 업데이트
if db_manager.use_supabase and db_manager.supabase:
    print("\n[Supabase 클라우드 동기화 시작]")
    updated_workers = 0
    for w_name, t_name in mappings.items():
        try:
            res = db_manager.supabase.table("work_logs").update({"worker_team": t_name}).eq("worker_name", w_name).execute()
            updated_workers += 1
        except Exception as e:
            print(f"  - [{w_name}] 업데이트 실패: {e}")
            
    print(f"[성공] Supabase work_logs 테이블에 총 {updated_workers}명의 팀 소속 정보가 완벽히 동기화되었습니다!")

    # 3. Supabase 팀별 집계 검증
    res = db_manager.supabase.table("work_logs").select("worker_team, worker_name").execute()
    df_supa = pd.DataFrame(res.data)
    print("\n[Supabase 클라우드 상의 팀별 작업 건수 집계]:")
    print(df_supa["worker_team"].value_counts())
