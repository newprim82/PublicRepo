import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.parser.kakao_parser import parse_duration_to_minutes
from src.parser.reply_matcher import WorkLogMatcher

def test_day_parsing():
    test_cases = [
        ("3days", 3 * 9 * 60),          # 27h = 1620m
        ("3day 예정", 3 * 9 * 60),      # 27h = 1620m
        ("1day", 1 * 9 * 60),           # 9h = 540m
        ("1일", 1 * 9 * 60),            # 9h = 540m
        ("2.5days", int(2.5 * 9 * 60)), # 22.5h = 1350m
        ("1day 4시간", (1*9 + 4) * 60), # 13h = 780m
        ("3일 30분", (3*9)*60 + 30),    # 27h 30m = 1650m
        ("5시간 30분 완료", 330),
        ("3days 완료", 3 * 9 * 60)
    ]

    for text, expected in test_cases:
        res = parse_duration_to_minutes(text)
        print(f"표현식: '{text}' -> {res}분 ({res/60}시간) | 기대치: {expected}분")
        assert res == expected, f"불일치: {res} != {expected}"

    sample_chat = """
--------------- 2026년 8월 31일 월요일 ---------------
[상상인 김시우 사원 / 기술 1팀] [오전 9:00] 작업 / 김시우 / KDB생명 / 데이터센터 이설 지원 / 3days 예정
[상상인 김시우 사원 / 기술 1팀] [오후 6:00] 3days 완료
[상상인 전종필 차장 / 기술 1팀] [오전 10:00] 지원 / 전종필 / 현대자동차 / 긴급 기술지원 / 1day 예정
[상상인 전종필 차장 / 기술 1팀] [오후 7:00] 1day 완료
"""

    records = WorkLogMatcher.parse_and_match_text(sample_chat)
    print("\n=== 대화 파싱 결과 ===")
    for r in records:
        print(f"{r.worker_name} | {r.client_name} | {r.task_description} | 예정: {r.estimated_minutes/60}h | 소요: {r.actual_minutes/60}h")
        if r.worker_name == "김시우":
            assert r.actual_minutes == 27 * 60, f"김시우 27h 불일치: {r.actual_minutes/60}h"
        if r.worker_name == "전종필":
            assert r.actual_minutes == 9 * 60, f"전종필 9h 불일치: {r.actual_minutes/60}h"

    print("\n[SUCCESS] 1day = 9시간 기준 파싱 및 대화 매칭 완벽 검증 성공!")

if __name__ == "__main__":
    test_day_parsing()
