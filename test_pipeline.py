import sys
from pathlib import Path
sys.path.insert(0, r"c:\Python\work-time-dashboard")

from src.parser.reply_matcher import WorkLogMatcher
from src.database.supabase_client import db_manager
from src.analytics.stats_service import StatsService

def test_pipeline():
    sample_file = Path(r"c:\Python\work-time-dashboard\sample_data\sample_kakao_chat.txt")
    with open(sample_file, "r", encoding="utf-8") as f:
        text = f.read()

    records = WorkLogMatcher.parse_and_match_text(text)
    print(f"[TEST 1] 파싱된 작업 건수: {len(records)}")
    assert len(records) > 0, "파싱 결과가 비어있습니다."

    for r in records:
        print(f"  [{r.status}] {r.worker_name} ({r.worker_company} {r.worker_title}) | {r.client_name} | {r.task_description} | {r.actual_minutes}분 (예정: {r.estimated_minutes}분) | 야간: {r.is_night_work}, 주말: {r.is_weekend_work}")

    saved = db_manager.save_work_logs(records)
    print(f"[TEST 2] DB 저장 성공: {saved}건")

    df = db_manager.fetch_all_work_logs()
    print(f"[TEST 3] DB 조회 행 수: {len(df)}")
    assert len(df) == len(records), "DB 조회 행 수가 일치하지 않습니다."

    kpis = StatsService.compute_kpis(df)
    print(f"[TEST 4] KPI 지표: {kpis}")

    worker_summary = StatsService.get_worker_summary(df)
    print(f"[TEST 5] 팀원별 요약:\n{worker_summary[['worker_name', 'total_hours', 'total_tasks', 'night_tasks']]}")

    print("\n[SUCCESS] 모든 파이프라인 테스트 성공!")

if __name__ == "__main__":
    test_pipeline()
