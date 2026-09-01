import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.parser.reply_matcher import WorkLogMatcher
from src.database.supabase_client import db_manager
from src.analytics.stats_service import StatsService

test_chat = """
--------------- 2026년 7월 24일 금요일 ---------------
[상상인 김시우 사원 / 기술 1팀] [오전 8:55] 기타 / 김시우 / 수협 / 상주지원 / 9시간

--------------- 2026년 7월 27일 월요일 ---------------
[상상인 김시우 사원 / 기술 1팀] [오전 7:17] 기타 / 김시우 / 한화손해보험 / VPN 장비 실사 / 11시간 예정

--------------- 2026년 7월 28일 화요일 ---------------
[상상인 김시우 사원 / 기술 1팀] [오전 7:34] 기타 / 김시우 / 한화손해보험 / VPN 장비 실사 / 11시간 예정
[상상인 김시우 사원 / 기술 1팀] [오후 6:34] 11시간 완료

--------------- 2026년 8월 16일 일요일 ---------------
[상상인 김시우 사원 / 기술 1팀] [오전 10:17] 기타 / 김시우 / BGF로지스 / 8월 검수서 작성 / 3시간 완료 (07시~10시)
"""

records = WorkLogMatcher.parse_and_match_text(test_chat)
print(f"파싱 결과 총 {len(records)}건:")
for r in records:
    print(f"  - [{r.status}] {r.start_time.strftime('%Y-%m-%d %H:%M')} | {r.worker_name} | {r.client_name} | {r.task_description} | 예정: {r.estimated_minutes/60}h | 소요: {r.actual_minutes/60}h")

# DB 저장 및 KPI 연산 테스트
db_manager.clear_all_data()
db_manager.save_work_logs(records)
df = db_manager.fetch_all_work_logs()
kpi = StatsService.compute_kpis(df)

print(f"\n[KPI 검증]:")
print(f"  - 총 지원 시간: {kpi['total_hours']}h (기대치: 11h(한화) + 3h(BGF) = 14.0h, 수협 9h 미포함!)")
print(f"  - 총 작업 건수: {kpi['total_tasks']}건 (완료 {kpi['completed_tasks']}건 / 진행 {kpi['pending_tasks']}건)")

assert kpi['total_hours'] == 14.0, f"총 지원 시간이 14.0h가 아닙니다: {kpi['total_hours']}h"
assert kpi['pending_tasks'] == 1, f"PENDING 건수가 1건이 아닙니다: {kpi['pending_tasks']}"
assert kpi['completed_tasks'] == 2, f"COMPLETED 건수가 2건이 아닙니다: {kpi['completed_tasks']}"

print("\n[SUCCESS] 모든 엣지 케이스 및 시간 집계 완벽 검증 완료!")
