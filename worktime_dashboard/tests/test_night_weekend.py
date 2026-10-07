# -*- coding: utf-8 -*-
import unittest
from datetime import datetime, timedelta
from src.parser.reply_matcher import check_is_night_work, check_is_weekend_work


class TestNightWeekendLogic(unittest.TestCase):
    """야간(22시~06시 1시간 이상) 및 주말(1시간 이상) 판정 핵심 로직 단위 테스트"""

    def test_daytime_weekday(self):
        # 2026-10-07(수) 10:00 ~ 12:00 (2시간)
        st = datetime(2026, 10, 7, 10, 0)
        ed = datetime(2026, 10, 7, 12, 0)
        self.assertFalse(check_is_night_work(st, ed, actual_minutes=120))
        self.assertFalse(check_is_weekend_work(st, ed, actual_minutes=120))

    def test_night_work_over_one_hour(self):
        # 2026-10-07(수) 23:00 ~ 01:00 (2시간 야간 근무)
        st = datetime(2026, 10, 7, 23, 0)
        ed = datetime(2026, 10, 8, 1, 0)
        self.assertTrue(check_is_night_work(st, ed, actual_minutes=120))
        self.assertFalse(check_is_weekend_work(st, ed, actual_minutes=120))

    def test_night_work_under_one_hour_fails(self):
        # 2026-10-07(수) 22:15 ~ 22:45 (30분 근무 -> 1시간 미만이므로 야간 불인정)
        st = datetime(2026, 10, 7, 22, 15)
        ed = datetime(2026, 10, 7, 22, 45)
        self.assertFalse(check_is_night_work(st, ed, actual_minutes=30))

    def test_night_work_boundary_overlap(self):
        # 2026-10-07(수) 21:00 ~ 23:00 (야간 구간 22:00~23:00 딱 1시간 근무 -> 야간 인정)
        st = datetime(2026, 10, 7, 21, 0)
        ed = datetime(2026, 10, 7, 23, 0)
        self.assertTrue(check_is_night_work(st, ed, actual_minutes=120))

    def test_friday_night_to_saturday_weekend_recognition(self):
        # 2026-10-09(금) 23:00 ~ 2026-10-10(토) 02:00 (토요일 2시간 근무 -> 주말 인정, 야간 인정)
        st = datetime(2026, 10, 9, 23, 0)
        ed = datetime(2026, 10, 10, 2, 0)
        self.assertTrue(check_is_night_work(st, ed, actual_minutes=180))
        self.assertTrue(check_is_weekend_work(st, ed, actual_minutes=180))

    def test_multiday_keyword_excludes_night_work(self):
        # 2026-10-07(수) 22:00 시작이지만 "3days" 표기된 경우 야간에서 제외
        st = datetime(2026, 10, 7, 22, 0)
        ed = datetime(2026, 10, 8, 2, 0)
        self.assertFalse(check_is_night_work(st, ed, raw_message="고객사 지원 3days", actual_minutes=240))


if __name__ == "__main__":
    unittest.main()
