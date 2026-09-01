import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.services.team_service import TeamService, DEFAULT_TEAMS
from src.database.supabase_client import db_manager

print(f"기본 팀 목록: {DEFAULT_TEAMS}")
mappings = TeamService.get_team_mappings()
print(f"현재 팀 매핑 수: {len(mappings)}명")

# 기존 work_logs에서 팀원 목록 불러와서 자동 초기화
df = db_manager.fetch_all_work_logs()
all_workers = sorted(df["worker_name"].dropna().unique())
print(f"총 활동 팀원 수: {len(all_workers)}명")

TeamService.auto_init_mappings_from_worklogs(all_workers, df)
mappings_after = TeamService.get_team_mappings()
print(f"초기화 후 팀 매핑 수: {len(mappings_after)}명")

for team in DEFAULT_TEAMS:
    members = [w for w, t in mappings_after.items() if t == team]
    print(f"  [{team}] ({len(members)}명): {', '.join(members[:10])}")
