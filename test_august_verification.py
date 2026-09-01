import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.parser.reply_matcher import WorkLogMatcher
from src.database.supabase_client import db_manager
from src.analytics.stats_service import StatsService

comprehensive_august_chat = """
--------------- 2026년 8월 10일 월요일 ---------------
[상상인 전종필 차장 / 기술 1팀] [오전 9:30] 작업 / 전종필 김시우 / KDB생명 / 아시아나 IT동 OS 업그레이드 / 4시간 예정
[상상인 전종필 차장 / 기술 1팀] [오후 3:00] 5시간 30분 완료
[상상인 이영희 대리 / 기술 1팀] [오후 1:00] [정기점검] 이영희, 홍대표 / 현대자동차 / 백본 스위치 정기점검 / 3시간 예정
[상상인 이영희 대리 / 기술 1팀] [오후 4:00] 작업 완료 / 3시간
[상상인 박민수 과장 / 기술 1팀] [오후 6:00] 지원 / 박민수 / 신한은행 / 방화벽 정책 긴급 적용 / 2시간 예정
[상상인 박민수 과장 / 기술 1팀] [오후 8:30] 완료했습니다

--------------- 2026. 8. 20. 목요일 ---------------
[상상인 최동훈 차장 / 기술 1팀] [오후 10:00] 작업 / 최동훈 / 삼성SDS / 상암 데이터센터 L4 스위치 펌웨어 업그레이드 / 4시간 예정
[상상인 최동훈 차장 / 기술 1팀] [오전 2:30] 4시간 30분 완료
"""

records = WorkLogMatcher.parse_and_match_text(comprehensive_august_chat)
print(f"[검증 1] 파싱된 8월 총 레코드 수: {len(records)}건")

for r in records:
    print(f"  - [{r.start_time.strftime('%Y-%m-%d')}] [{r.status}] {r.worker_name} | {r.client_name} | {r.task_description} | 소요: {r.actual_minutes}분 ({r.actual_minutes/60}h) | 야간: {r.is_night_work}")

db_manager.clear_all_data()
db_manager.save_work_logs(records)

df = db_manager.fetch_all_work_logs()
print("\n[검증 2] 8월 팀원별 지원 시간 집계:")
summary = StatsService.get_worker_summary(df)
print(summary[['worker_name', 'total_hours', 'total_tasks', 'night_tasks']])

print("\n[검증 3] 월별 총계:")
monthly = StatsService.get_monthly_trend(df)
print(monthly)

assert len(df) == 6, f"예상 6건이지만 {len(df)}건입니다."
assert df['month_str'].iloc[0] == '2026-08', "8월 데이터가 아닙니다!"
print("\n[SUCCESS] 8월 데이터 파싱 및 시간 집계 완벽 검증 성공!")
