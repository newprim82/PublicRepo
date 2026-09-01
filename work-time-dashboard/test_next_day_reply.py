import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.parser.reply_matcher import WorkLogMatcher

def test_next_day_reply():
    # 사용자가 실제 카톡에서 올린 상황 시뮬레이션
    sample_chat = """
--------------- 2026년 7월 27일 월요일 ---------------
[상상인 김시우 사원 / 기술 1팀] [오전 7:17] 작업 / 김시우 / 한화손해보험 / VPN 장비 실사 / 11시간 예정

--------------- 2026년 7월 28일 화요일 ---------------
[상상인 김시우 사원 / 기술 1팀] [오전 7:34] 상상인 김시우 사원 / 기술 1팀에게 답장
작업 / 김시우 / 한화손해보험 / VPN 장비 실사 / 11시간 예정
11시간 완료
"""

    records = WorkLogMatcher.parse_and_match_text(sample_chat)
    print(f"[검증] 파싱된 총 레코드 수: {len(records)}건")
    
    for r in records:
        print(f"  - [{r.status}] {r.start_time.strftime('%Y-%m-%d %H:%M')} | {r.worker_name} | {r.client_name} | {r.task_description} | 예정: {r.estimated_minutes/60}h | 소요: {r.actual_minutes/60}h")

    # 결과 검증: 2건이 아니라 정확히 1건의 COMPLETED로 병합되어야 함!
    assert len(records) == 1, f"예상 1건이지만 {len(records)}건으로 분리되었습니다!"
    assert records[0].status == "COMPLETED", f"상태가 COMPLETED가 아닙니다: {records[0].status}"
    assert records[0].start_time.strftime('%Y-%m-%d %H:%M') == "2026-07-27 07:17", "시작 시간이 7월 27일 07:17이 아닙니다!"
    assert records[0].actual_minutes == 11 * 60, f"소요 시간이 11시간이 아닙니다: {records[0].actual_minutes/60}h"

    print("\n[SUCCESS] 다음날 답장 완료 보고가 완벽하게 1건의 COMPLETED로 병합 매칭되었습니다!")

if __name__ == "__main__":
    test_next_day_reply()
