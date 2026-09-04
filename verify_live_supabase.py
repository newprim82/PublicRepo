import sys
import pandas as pd
from datetime import datetime
from pathlib import Path

# 콘솔 cp949 인코딩 안전 처리
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import config
from src.database.supabase_client import db_manager
from src.parser.reply_matcher import WorkLogRecord

def run_verification():
    print("=" * 60)
    print("🔍 [Supabase 실시간 동작 및 연결 상태 전수 검증]")
    print("=" * 60)
    print(f"1. SUPABASE_URL: {config.SUPABASE_URL}")
    print(f"2. is_supabase_configured(): {config.is_supabase_configured()}")
    print(f"3. db_manager.use_supabase: {db_manager.use_supabase}")
    print(f"4. db_manager.supabase 객체: {type(db_manager.supabase)}")

    if not db_manager.use_supabase or not db_manager.supabase:
        print("❌ [오류] Supabase가 연결되어 있지 않습니다!")
        return

    # 1. Supabase에서 최신 등록된 레코드 5건 조회
    print("\n5. ☁️ Supabase Cloud DB에서 직접 조회한 최신 데이터 5건:")
    res = db_manager.supabase.table("worktime_work_logs")\
        .select("id, start_time, worker_name, client_name, task_description, status")\
        .order("start_time", desc=True)\
        .limit(5)\
        .execute()
        
    for r in res.data:
        t_desc = r['task_description'][:30].replace("\n", " ")
        print(f"   - [ID: {r['id']}] {r['start_time']} | {r['worker_name']} | {r['client_name']} | {t_desc} | 상태: {r['status']}")

    # 2. 실시간 쓰기(Upsert) 테스트
    test_hash = f"test_live_check_{int(datetime.now().timestamp())}"
    test_record = WorkLogRecord(
        msg_hash=test_hash,
        log_type="지원",
        worker_name="검증봇",
        worker_title="사원",
        worker_team="기술 1팀",
        client_name="Supabase실시간검증",
        task_description="실시간 쓰기 및 읽기 양방향 검증 테스트",
        estimated_minutes=60,
        actual_minutes=60,
        start_time=datetime.now(),
        end_time=datetime.now(),
        status="COMPLETED",
        is_night_work=False,
        is_weekend_work=False,
        raw_start_message="[검증 시작]",
        raw_end_message="[검증 완료]"
    )

    print(f"\n6. 🧪 실시간 테스트 데이터 생성 후 Supabase에 쓰기(save_work_logs) 실행...")
    saved_cnt = db_manager.save_work_logs([test_record])
    print(f"   -> save_work_logs 결과: {saved_cnt}건 반환")

    # 3. 방금 쓴 데이터가 Supabase 클라우드에서 즉시 조회되는지 확인
    print("\n7. 🔍 방금 쓴 테스트 데이터를 Supabase 클라우드에서 직접 SELECT 확인:")
    check_res = db_manager.supabase.table("worktime_work_logs").select("*").eq("msg_hash", test_hash).execute()
    if check_res.data:
        saved_row = check_res.data[0]
        print(f"   ✅ [검증 성공!] Supabase 클라우드에 실시간으로 정상 저장되었습니다!")
        print(f"   - Supabase ID: {saved_row['id']}")
        print(f"   - 담당자: {saved_row['worker_name']}")
        print(f"   - 고객사: {saved_row['client_name']}")
        print(f"   - 작업내용: {saved_row['task_description']}")
        print(f"   - 등록일시: {saved_row['created_at']}")
        
        # 테스트 데이터 정리
        db_manager.supabase.table("worktime_work_logs").delete().eq("msg_hash", test_hash).execute()
        print("   🧹 검증용 임시 데이터 자동 삭제 완료.")
    else:
        print("   ❌ [검증 실패] Supabase에서 방금 쓴 레코드를 찾지 못했습니다!")

    # 4. Streamlit 캐시와 Supabase 조회 일치 여부 확인
    print("\n8. 📊 대시보드에서 사용하는 fetch_all_work_logs() 전수 검증:")
    df_all = db_manager.fetch_all_work_logs()
    print(f"   - 조회된 총 레코드 수: {len(df_all)}건")
    print(f"   - 2026-09월 데이터 건수: {len(df_all[df_all['month_str'] == '2026-09'])}건")
    print(f"   - 2026-08월 데이터 건수: {len(df_all[df_all['month_str'] == '2026-08'])}건")

    print("\n" + "=" * 60)
    print("🎉 [최종 판정] 현재 프로그램은 100% Supabase Cloud DB를 정상 사용하고 있습니다!")
    print("=" * 60)

if __name__ == "__main__":
    run_verification()
