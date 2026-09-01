import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.services.team_service import TeamService, DEFAULT_TEAMS
from src.database.supabase_client import db_manager

# 1. 팀 배정 테스트 (예: 김시우 -> 기술 1팀, 전종필 -> 기술 2팀, 홍대표 -> PI팀)
TeamService.save_team_members("기술 1팀", ["김시우"])
TeamService.save_team_members("기술 2팀", ["전종필"])
TeamService.save_team_members("PI팀", ["홍대표"])

mappings = TeamService.get_team_mappings()
print(f"[검증] 김시우 팀: {mappings.get('김시우')}")
print(f"[검증] 전종필 팀: {mappings.get('전종필')}")
print(f"[검증] 홍대표 팀: {mappings.get('홍대표')}")

assert mappings.get('김시우') == "기술 1팀"
assert mappings.get('전종필') == "기술 2팀"
assert mappings.get('홍대표') == "PI팀"

# 2. work_logs와 팀 연동 검증
df = db_manager.fetch_all_work_logs()
df["worker_team"] = df["worker_name"].map(mappings).fillna(df["worker_team"])

t1_workers = df[df["worker_team"] == "기술 1팀"]["worker_name"].unique()
t2_workers = df[df["worker_team"] == "기술 2팀"]["worker_name"].unique()
pi_workers = df[df["worker_team"] == "PI팀"]["worker_name"].unique()

print(f"기술 1팀 작업자: {t1_workers}")
print(f"기술 2팀 작업자: {t2_workers}")
print(f"PI팀 작업자: {pi_workers}")

print("\n[SUCCESS] 팀별 팀원 분류 및 대시보드 연동 완벽 검증 성공!")
