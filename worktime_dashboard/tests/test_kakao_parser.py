# -*- coding: utf-8 -*-
import unittest
from datetime import datetime
from src.parser.kakao_parser import (
    parse_duration_to_minutes,
    KakaoMessageParser,
    RawKakaoMessage
)


class TestKakaoParser(unittest.TestCase):
    """카카오톡 메시지 소요시간 및 시작/종료 파싱 단위 테스트"""

    def test_duration_parsing(self):
        # 시간 단위
        self.assertEqual(parse_duration_to_minutes("2시간"), 120)
        self.assertEqual(parse_duration_to_minutes("1.5시간"), 90)
        self.assertEqual(parse_duration_to_minutes("30분"), 30)
        self.assertEqual(parse_duration_to_minutes("1시간 30분"), 90)

        # 시간 범위 (10:00 ~ 12:30)
        self.assertEqual(parse_duration_to_minutes("10:00 ~ 12:30"), 150)
        self.assertEqual(parse_duration_to_minutes("23:00-01:00"), 120)

        # Day 단위: 1day = 540분(9시간)
        self.assertEqual(parse_duration_to_minutes("1day"), 540)
        self.assertEqual(parse_duration_to_minutes("2days"), 1080)
        self.assertEqual(parse_duration_to_minutes("1일"), 540)

    def test_start_message_parsing_slash_format(self):
        # 표준 5개 필드: 구분 / 작업자 / 고객사 / 작업내용 / 예정시간
        msg = RawKakaoMessage(
            raw_text="지원 / 홍길동 / KB신용정보 / 방화벽 정책 작업 / 2시간",
            sender_profile="홍길동/대리/네트워크팀",
            timestamp=datetime(2026, 10, 7, 10, 0),
            content="지원 / 홍길동 / KB신용정보 / 방화벽 정책 작업 / 2시간"
        )
        parsed_starts = KakaoMessageParser.parse_task_starts(msg)
        self.assertTrue(len(parsed_starts) > 0)
        task = parsed_starts[0]
        self.assertEqual(task.worker_name, "홍길동")
        self.assertEqual(task.client_name, "KB신용정보")
        self.assertEqual(task.estimated_minutes, 120)
        self.assertEqual(task.log_type, "지원")

    def test_start_message_parsing_bracket_format(self):
        # 대괄호 구분자: [지원] 홍길동 / KB신용정보 / 스위치 점검 / 1시간
        msg = RawKakaoMessage(
            raw_text="[지원] 홍길동 / KB신용정보 / 스위치 점검 / 1시간",
            sender_profile="홍길동/대리/네트워크팀",
            timestamp=datetime(2026, 10, 7, 14, 0),
            content="[지원] 홍길동 / KB신용정보 / 스위치 점검 / 1시간"
        )
        parsed_starts = KakaoMessageParser.parse_task_starts(msg)
        self.assertTrue(len(parsed_starts) > 0)
        task = parsed_starts[0]
        self.assertEqual(task.worker_name, "홍길동")
        self.assertEqual(task.client_name, "KB신용정보")
        self.assertEqual(task.estimated_minutes, 60)

    def test_end_message_with_duration(self):
        # 시간 명시 완료: 2시간 30분 소요 완료
        msg = RawKakaoMessage(
            raw_text="2시간 30분 소요 완료",
            sender_profile="홍길동/대리/네트워크팀",
            timestamp=datetime(2026, 10, 7, 12, 30),
            content="2시간 30분 소요 완료"
        )
        parsed_end = KakaoMessageParser.parse_task_end(msg)
        self.assertIsNotNone(parsed_end)
        self.assertEqual(parsed_end.actual_minutes, 150)
        self.assertTrue(parsed_end.is_explicit_time)

    def test_end_message_simple(self):
        # 단순 완료
        msg = RawKakaoMessage(
            raw_text="작업 완료했습니다",
            sender_profile="홍길동/대리/네트워크팀",
            timestamp=datetime(2026, 10, 7, 12, 0),
            content="작업 완료했습니다"
        )
        parsed_end = KakaoMessageParser.parse_task_end(msg)
        self.assertIsNotNone(parsed_end)
        self.assertEqual(parsed_end.actual_minutes, 0)
        self.assertFalse(parsed_end.is_explicit_time)


if __name__ == "__main__":
    unittest.main()
