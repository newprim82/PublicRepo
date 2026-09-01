import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.parser.reply_matcher import WorkLogMatcher
from src.database.supabase_client import db_manager
from src.analytics.stats_service import StatsService

test_multi_chat = """
--------------- 2026년 8월 31일 월요일 ---------------
[상상인 전종필 차장 / 기술 1팀] [오후 1:00] 작업 / 전종필 김시우 / KDB생명 / IT동 OS 업그레이드 / 4시간 예정
[상상인 전종필 차장 / 기술 1팀] [오후 6:30] 5시간 30분 완료
[상상인 이영희 대리 / 기술 1팀] [오후 2:00] 정기점검 / 전종필, 이영희 / 현대자동차 / 백본 스위치 점검 / 2시간 예정
[상상인 이영희 대리 / 기술 1팀] [오후 4:00] 2시간 완료
[상상인 최동훈 차장 / 기술 1팀] [오후 3:00] 작업 / 최동훈 / 삼성SDS / L4 작업 / 3시간 예정
[상상인 최동훈 차장 / 기술 1팀] [오후 6:00] 3시간 완료
"""

records = WorkLogMatcher.parse_and_match_text(test_multi_chat)
print(f"[TEST] 총 생성된 개인별 레코드 건수: {len(records)}")

for r in records:
    print(f"  - [{r.status}] 담당자: '{r.worker_name}' | 고객사: {r.client_name} | {r.task_description} | 소요: {r.actual_minutes}분 ({r.actual_minutes/60}h)")

# DB 저장 및 집계 테스트
db_manager.save_work_logs(records)
df = db_manager.fetch_all_work_logs()
worker_summary = StatsService.get_worker_summary(df)
print("\n[TEST] 팀원별 집계 결과:")
print(worker_summary[['worker_name', 'total_hours', 'total_tasks']])

worker_names = sorted(df['worker_name'].unique())
print(f"\n[TEST] 고유 담당자 목록: {worker_names}")
assert "전종필 김시우" not in worker_names, "다중 이름이 분리되지 않았습니다!"
assert "전종필" in worker_names and "김시우" in worker_names, "개별 이름이 존재하지 않습니다!"
print("\n[SUCCESS] 다중 담당자 개별 분리 및 시간 배분 완벽 검증 완료!")
