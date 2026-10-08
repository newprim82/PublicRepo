# -*- coding: utf-8 -*-
import unittest
from datetime import datetime, timedelta
import pandas as pd
from src.services.schedule_sync_service import ScheduleSyncService

class TestScheduleSyncService(unittest.TestCase):
    """라이브 관제 승격 정책 및 카톡-아웃룩 중복 제거 단위 테스트"""

    def test_upcoming_not_promoted_before_start_time(self):
        """시작 시각(예: 09:00) 전에는 상단 진행 중으로 승격되지 않고 예정 일정에만 머무르는지 검증"""
        now = datetime.now()
        # 시작 시각: 10분 뒤 (아직 시작 전)
        future_st = now + timedelta(minutes=10)
        future_ed = future_st + timedelta(hours=2)

        outlook_df = pd.DataFrame([{
            "entry_id": "TEST_OUT_1",
            "worker_name": "홍길동",
            "subject": "[홍길동] IM뱅크 정기점검",
            "start_time": future_st,
            "end_time": future_ed,
            "duration_hours": 2.0,
            "is_leave": False,
            "is_all_day": False
        }])

        pend_df, sched_df, comp_df, auto_comp_df, leaves = ScheduleSyncService.get_synced_live_tasks(
            kakao_pend_df=pd.DataFrame(),
            today_completed_df=pd.DataFrame(),
            kakao_sched_df=pd.DataFrame(),
            outlook_df=outlook_df
        )

        # 시작 전이므로 상단 진행 중(pend_df)에는 절대 없어야 함!
        self.assertTrue(pend_df.empty, "시작 시각 이전 작업이 진행 중(pend_df)에 포함되면 안 됩니다.")
        # 하단 예정 일정(sched_df)에 1건 존재해야 함!
        self.assertEqual(len(sched_df), 1)
        self.assertEqual(sched_df.iloc[0]["worker_name"], "홍길동")
        self.assertEqual(sched_df.iloc[0]["status"], "SCHEDULED")

    def test_promoted_to_pending_after_start_time(self):
        """시작 시각(예: 10분 전 시작)이 지나면 정상적으로 진행 중(PENDING)으로 승격되는지 검증"""
        now = datetime.now()
        past_st = now - timedelta(minutes=10)
        future_ed = now + timedelta(hours=1)

        outlook_df = pd.DataFrame([{
            "entry_id": "TEST_OUT_2",
            "worker_name": "김형일",
            "subject": "[김형일] IM뱅크 업무지원",
            "start_time": past_st,
            "end_time": future_ed,
            "duration_hours": 2.0,
            "is_leave": False,
            "is_all_day": False
        }])

        pend_df, sched_df, comp_df, auto_comp_df, leaves = ScheduleSyncService.get_synced_live_tasks(
            kakao_pend_df=pd.DataFrame(),
            today_completed_df=pd.DataFrame(),
            kakao_sched_df=pd.DataFrame(),
            outlook_df=outlook_df
        )

        # 시작 시각이 지났으므로 진행 중(pend_df)으로 승격되어야 함!
        self.assertEqual(len(pend_df), 1)
        self.assertEqual(pend_df.iloc[0]["worker_name"], "김형일")
        self.assertEqual(pend_df.iloc[0]["status"], "PENDING")
        self.assertTrue(sched_df.empty)

    def test_dedup_between_kakao_sched_and_outlook(self):
        """카카오톡 예정 일정에 이미 있는 동일 작업은 아웃룩 일정이 중복 생성되지 않는지 검증"""
        now = datetime.now()
        future_st = now + timedelta(minutes=15)
        future_ed = future_st + timedelta(hours=8)

        # 카카오톡 예정 일정 (SCHEDULED)
        kakao_sched = pd.DataFrame([{
            "worker_name": "문영민",
            "client_name": "IM뱅크",
            "task_description": "업무지원 (3/3일차)",
            "start_time": future_st,
            "end_time": future_ed,
            "status": "SCHEDULED"
        }])

        # 아웃룩 일정 (대구은행 고도화 업무지원)
        outlook_df = pd.DataFrame([{
            "entry_id": "TEST_OUT_3",
            "worker_name": "문영민",
            "subject": "[문영민] 대구은행 고도화 프로젝트 업무지원",
            "start_time": future_st,
            "end_time": future_ed,
            "duration_hours": 8.0,
            "is_leave": False,
            "is_all_day": False
        }])

        pend_df, sched_df, comp_df, auto_comp_df, leaves = ScheduleSyncService.get_synced_live_tasks(
            kakao_pend_df=pd.DataFrame(),
            today_completed_df=pd.DataFrame(),
            kakao_sched_df=kakao_sched,
            outlook_df=outlook_df
        )

        # 중복 방지로 인해 예정 일정에는 단 1건만 존재해야 하고, has_both 플래그가 True여야 함
        self.assertEqual(len(sched_df), 1)
        self.assertTrue(sched_df.iloc[0]["has_both"])
        self.assertTrue(pend_df.empty)

if __name__ == "__main__":
    unittest.main()
