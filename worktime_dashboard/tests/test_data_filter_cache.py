import unittest
import pandas as pd
from src.dashboard.app import get_cached_filtered_data, NON_DATA_PAGES

class TestDataFilterCache(unittest.TestCase):
    def setUp(self):
        self.sample_df = pd.DataFrame([
            {
                "worker_name": "홍길동",
                "worker_team": "기술 1팀",
                "worker_title": "대리",
                "client_name": "고객사A",
                "log_type": "정기점검",
                "month_str": "2026-10",
                "is_night_work": False,
                "is_weekend_work": False,
                "actual_hours": 3.0
            },
            {
                "worker_name": "이순신",
                "worker_team": "기술 2팀",
                "worker_title": "과장",
                "client_name": "고객사B",
                "log_type": "긴급장애",
                "month_str": "2026-10",
                "is_night_work": True,
                "is_weekend_work": False,
                "actual_hours": 4.5
            },
            {
                "worker_name": "강감찬",
                "worker_team": "기술 1팀",
                "worker_title": "사원",
                "client_name": "고객사A",
                "log_type": "기술지원",
                "month_str": "2026-09",
                "is_night_work": False,
                "is_weekend_work": True,
                "actual_hours": 2.0
            }
        ])

    def test_non_data_pages_definition(self):
        """비데이터 관리자 페이지 상수 확인"""
        self.assertIn("📅 법정 및 임시 공휴일 관리", NON_DATA_PAGES)
        self.assertIn("👥 시스템 관리자 계정 관리", NON_DATA_PAGES)
        self.assertIn("🔐 시스템 로그인", NON_DATA_PAGES)
        self.assertIn("⚙️ 팀원 소속 및 직급 관리 (팀 생성/배정)", NON_DATA_PAGES)

    def test_filter_all_teams(self):
        """전체 팀 조회 필터 검증"""
        df_final, df_base = get_cached_filtered_data(
            _df_raw=self.sample_df,
            selected_team="전체 팀",
            team_workers=("홍길동", "이순신", "강감찬"),
            selected_workers=("홍길동", "이순신", "강감찬"),
            selected_clients=("고객사A", "고객사B"),
            selected_types=("정기점검", "긴급장애", "기술지원"),
            title_mode="전체 직급",
            selected_titles=("사원", "대리", "과장", "수석"),
            night_only=False,
            weekend_only=False,
            selected_months=("2026-10", "2026-09"),
            title_mappings_tuple=()
        )
        self.assertEqual(len(df_final), 3)
        self.assertEqual(len(df_base), 3)

    def test_filter_single_team_and_month(self):
        """특정 팀 및 특정 월 슬라이싱 검증"""
        df_final, df_base = get_cached_filtered_data(
            _df_raw=self.sample_df,
            selected_team="기술 1팀",
            team_workers=("홍길동", "강감찬"),
            selected_workers=("홍길동", "강감찬"),
            selected_clients=("고객사A", "고객사B"),
            selected_types=("정기점검", "긴급장애", "기술지원"),
            title_mode="전체 직급",
            selected_titles=("사원", "대리", "과장", "수석"),
            night_only=False,
            weekend_only=False,
            selected_months=("2026-10",),
            title_mappings_tuple=()
        )
        self.assertEqual(len(df_final), 1)
        self.assertEqual(df_final.iloc[0]["worker_name"], "홍길동")
        self.assertEqual(len(df_base), 2)  # 홍길동 + 강감찬 (월 필터 전 베이스)

    def test_filter_night_only(self):
        """야간 전용 필터링 검증"""
        df_final, df_base = get_cached_filtered_data(
            _df_raw=self.sample_df,
            selected_team="전체 팀",
            team_workers=("홍길동", "이순신", "강감찬"),
            selected_workers=("홍길동", "이순신", "강감찬"),
            selected_clients=("고객사A", "고객사B"),
            selected_types=("정기점검", "긴급장애", "기술지원"),
            title_mode="전체 직급",
            selected_titles=("사원", "대리", "과장", "수석"),
            night_only=True,
            weekend_only=False,
            selected_months=("2026-10", "2026-09"),
            title_mappings_tuple=()
        )
        self.assertEqual(len(df_final), 1)
        self.assertEqual(df_final.iloc[0]["worker_name"], "이순신")

    def test_filter_empty_dataframe(self):
        """빈 데이터프레임 입력 시 안전 동작 검증"""
        empty_df = pd.DataFrame()
        df_final, df_base = get_cached_filtered_data(
            _df_raw=empty_df,
            selected_team="전체 팀",
            team_workers=(),
            selected_workers=(),
            selected_clients=(),
            selected_types=(),
            title_mode="전체 직급",
            selected_titles=(),
            night_only=False,
            weekend_only=False,
            selected_months=(),
            title_mappings_tuple=()
        )
        self.assertTrue(df_final.empty)
        self.assertTrue(df_base.empty)

if __name__ == "__main__":
    unittest.main()
