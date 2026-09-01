import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.database.supabase_client import db_manager

# 1. DB 초기화
db_manager.clear_all_data()
df = db_manager.fetch_all_work_logs()
print(f"[검증 1] 초기화 후 DB 레코드 수: {len(df)}건 (0건이어야 함)")
assert len(df) == 0, "DB 초기화 실패!"

# 2. 실제 사용자의 카톡 대화 시나리오 재현
chat_text = """
--------------- 2026년 7월 27일 월요일 ---------------
[상상인 김시우 사원 / 기술 1팀] [오전 7:17] 기타 / 전종필 김시우 / 한화손해보험 / VPN 장비 실사 / 11시간 예정

--------------- 2026년 7월 28일 화요일 ---------------
[상상인 김시우 사원 / 기술 1팀] [오전 7:34] 기타 / 전종필 김시우 / 한화손해보험 / VPN 장비 실사 / 11시간 예정
[상상인 김시우 사원 / 기술 1팀] [오후 6:35] 11시간 완료
"""

from src.parser.reply_matcher import WorkLogMatcher

records = WorkLogMatcher.parse_and_match_text(chat_text)
print(f"\n[검증 2] 파싱된 레코드 수: {len(records)}건 (전종필 1건 + 김시우 1건 = 총 2건)")

for r in records:
    print(f"  - [{r.status}] {r.start_time.strftime('%Y-%m-%d %H:%M')} | {r.worker_name} | {r.client_name} | {r.task_description} | 예정: {r.estimated_minutes/60}h | 소요: {r.actual_minutes/60}h")

db_manager.save_work_logs(records)
df2 = db_manager.fetch_all_work_logs()
print(f"\n[검증 3] DB 조회 레코드 수: {len(df2)}건")
for idx, r in df2.iterrows():
    print(f"  - [{r['status']}] {r['start_time']} | {r['worker_name']} | {r['client_name']} | 예정: {r['estimated_hours']}h | 소요: {r['actual_hours']}h")

assert len(df2) == 2, f"예상 2건이지만 {len(df2)}건입니다."
assert (df2["status"] == "COMPLETED").all(), "모두 COMPLETED 상태여야 합니다."
assert (df2["start_time"].dt.day == 27).all(), "모두 7월 27일(원래 시작 시각)이어야 합니다!"

print("\n[SUCCESS] 완료 건이 원래 시작 시각(Pending 시각)인 7월 27일로 완벽하게 귀속되었습니다!")
