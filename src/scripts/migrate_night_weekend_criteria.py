"""
야간 작업(18시 이후 시작 ~ 익일 09시, 1시간 이상) 및
주말 작업(주말 1시간 이상 포함 시 무조건 주말)
기준 개편에 따른 DB 일괄 마이그레이션 스크립트
"""

import os
import sys
import sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from src.config import config
from src.database.supabase_client import db_manager
from src.parser.reply_matcher import check_is_night_work, check_is_weekend_work


def run_migration():
    print("==================================================")
    print("🚀 [야간 & 주말 작업 기준 개편 DB 마이그레이션 시작]")
    print("==================================================")

    # 1. 전체 데이터 로드
    df = db_manager.fetch_all_work_logs()
    total_count = len(df)
    print(f"[*] 총 작업 로그 수: {total_count}건")
    if total_count == 0:
        print("[!] 마이그레이션할 데이터가 없습니다.")
        return

    # 2. 안전 전체 백업 파일 생성
    backup_dir = PROJECT_ROOT / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_csv = backup_dir / f"work_logs_backup_before_criteria_migration_{ts_str}.csv"
    backup_json = backup_dir / f"work_logs_backup_before_criteria_migration_{ts_str}.json"
    
    df.to_csv(backup_csv, index=False, encoding="utf-8-sig")
    df.to_json(backup_json, orient="records", force_ascii=False, indent=2)
    print(f"[✅ 백업 완료] {backup_csv.name} ({len(df)}건)")

    # 3. 새로운 야간 & 주말 판정 계산
    old_night_count = int(df["is_night_work"].sum())
    old_weekend_count = int(df["is_weekend_work"].sum())

    updates = []
    
    for idx, row in df.iterrows():
        r_id = row.get("id")
        msg_hash = row.get("msg_hash")
        
        start_time_val = row.get("start_time")
        if pd.isna(start_time_val) or not start_time_val:
            continue
            
        if isinstance(start_time_val, str):
            start_dt = pd.to_datetime(start_time_val)
        else:
            start_dt = start_time_val
            
        if hasattr(start_dt, "to_pydatetime"):
            start_dt = start_dt.to_pydatetime()
        if start_dt.tzinfo is not None:
            start_dt = start_dt.replace(tzinfo=None)

        act_min = int(row.get("actual_minutes") or 0)
        est_min = int(row.get("estimated_minutes") or 0)
        raw_msg = str(row.get("raw_start_message") or "") + " " + str(row.get("task_description") or "")

        # 새 판정 수행
        new_night = check_is_night_work(start_dt, None, raw_msg, est_min, act_min)
        new_weekend = check_is_weekend_work(start_dt, None, raw_msg, est_min, act_min)

        old_night = bool(row.get("is_night_work", False))
        old_weekend = bool(row.get("is_weekend_work", False))

        if (new_night != old_night) or (new_weekend != old_weekend):
            updates.append({
                "id": r_id,
                "msg_hash": msg_hash,
                "is_night_work": new_night,
                "is_weekend_work": new_weekend,
                "old_night": old_night,
                "old_weekend": old_weekend
            })

    print(f"[*] 상태 변경 대상 레코드: 총 {len(updates)}건")

    if not updates:
        print("[*] 변경 대상 레코드가 없습니다. (이미 최신 상태)")
        return

    # 4. 로컬 SQLite DB 업데이트
    local_db_path = config.LOCAL_DB_PATH
    if local_db_path.exists():
        conn = sqlite3.connect(str(local_db_path))
        cursor = conn.cursor()
        for u in updates:
            cursor.execute("""
                UPDATE work_logs 
                SET is_night_work = ?, is_weekend_work = ?
                WHERE id = ? OR msg_hash = ?
            """, (1 if u["is_night_work"] else 0, 1 if u["is_weekend_work"] else 0, u["id"], u["msg_hash"]))
        conn.commit()
        conn.close()
        print(f"[✅ 로컬 SQLite DB 갱신 완료] {len(updates)}건 업데이트")

    # 5. Supabase 클라우드 DB 업데이트
    if db_manager.use_supabase and db_manager.supabase is not None:
        print("[*] Supabase 클라우드 DB 동기화 업데이트 진행 중...")
        success_sb = 0
        
        batch_size = 50
        for i in range(0, len(updates), batch_size):
            chunk = updates[i:i + batch_size]
            for u in chunk:
                try:
                    db_manager.supabase.table("worktime_work_logs").update({
                        "is_night_work": u["is_night_work"],
                        "is_weekend_work": u["is_weekend_work"]
                    }).eq("msg_hash", u["msg_hash"]).execute()
                    success_sb += 1
                except Exception as e:
                    print(f"[!] Supabase 업데이트 에러 ({u['msg_hash']}): {e}")
            print(f"    진행률: {min(i + batch_size, len(updates))}/{len(updates)} 완료...")

        print(f"[✅ Supabase 클라우드 DB 갱신 완료] {success_sb}건 동기화 완료")

    # 6. 마이그레이션 후 통계 재검증
    new_df = db_manager.fetch_all_work_logs()
    new_night_count = int(new_df["is_night_work"].sum())
    new_weekend_count = int(new_df["is_weekend_work"].sum())

    print("\n==================================================")
    print("📊 [마이그레이션 최종 결과 보고]")
    print("==================================================")
    print(f"🌙 야간 작업: {old_night_count}건 ➔ {new_night_count}건 (변동: {new_night_count - old_night_count:+d}건)")
    print(f"🏖️ 주말 작업: {old_weekend_count}건 ➔ {new_weekend_count}건 (변동: {new_weekend_count - old_weekend_count:+d}건)")
    print(f"✨ 총 변경된 작업 로그: {len(updates)}건")
    print("==================================================\n")


if __name__ == "__main__":
    run_migration()
