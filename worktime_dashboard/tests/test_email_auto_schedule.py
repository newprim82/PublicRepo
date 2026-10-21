# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta

from src.services.email_schedule_service import EmailScheduleService
from src.services.email_dispatch_service import EmailDispatchService
from src.services.monthly_worklog_service import MonthlyWorklogService
from src.common.time_utils import get_current_kst_time


class TestEmailAutoSchedule(unittest.TestCase):
    def test_get_active_recipient_emails_no_import_error(self):
        """EmailScheduleService 수신자 조회 시 time_utils import 오류 없이 기본 수신자가 반환되는지 검증"""
        emails = EmailScheduleService.get_active_recipient_emails()
        self.assertTrue(isinstance(emails, list))
        self.assertGreaterEqual(len(emails), 1)
        self.assertIn("ymmoon@sangsanginworld.co.kr", [e.lower() for e in emails])

    def test_weekly_auto_dispatch_idempotency_guard(self):
        """금주 월요일 00:00 이후 AUTO_WEEKLY 성공 이력 유무에 따른 중복 발송 방지 가드 검증"""
        now_kst = get_current_kst_time()
        this_monday_noon = (now_kst - timedelta(days=now_kst.weekday())).replace(hour=8, minute=5, second=0)
        prev_week_dt = this_monday_noon - timedelta(days=7)

        with patch.object(
            EmailDispatchService,
            "get_recent_dispatches",
            return_value=[
                {
                    "dispatch_type": "AUTO_WEEKLY",
                    "selected_team": "기술 1팀",
                    "status": "SUCCESS",
                    "created_at": this_monday_noon.strftime("%Y-%m-%d %H:%M:%S"),
                }
            ],
        ):
            self.assertTrue(EmailDispatchService.has_weekly_auto_dispatched_this_week("기술 1팀"))
            self.assertFalse(EmailDispatchService.has_weekly_auto_dispatched_this_week("기술 2팀"))

        with patch.object(
            EmailDispatchService,
            "get_recent_dispatches",
            return_value=[
                {
                    "dispatch_type": "AUTO_WEEKLY",
                    "selected_team": "기술 1팀",
                    "status": "SUCCESS",
                    "created_at": prev_week_dt.strftime("%Y-%m-%d %H:%M:%S"),
                }
            ],
        ):
            self.assertFalse(EmailDispatchService.has_weekly_auto_dispatched_this_week("기술 1팀"))

    def test_monthly_auto_dispatch_idempotency_guard(self):
        """전월 대상 AUTO_MONTHLY 성공 이력 유무에 따른 중복 발송 방지 가드 검증"""
        with patch.object(
            MonthlyWorklogService,
            "get_recent_dispatches",
            return_value=[
                {
                    "team_name": "기술 1팀",
                    "target_month": "2026-09",
                    "dispatch_type": "AUTO_MONTHLY",
                    "status": "SUCCESS",
                }
            ],
        ):
            self.assertTrue(MonthlyWorklogService.has_monthly_auto_dispatched("기술 1팀", "2026-09"))
            self.assertFalse(MonthlyWorklogService.has_monthly_auto_dispatched("기술 1팀", "2026-10"))


if __name__ == "__main__":
    unittest.main()
