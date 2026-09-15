import sys
sys.path.insert(0, r"c:\Python\work-time-dashboard")
from src.database.supabase_client import db_manager
from src.parser.multiday_splitter import split_multiday_record, is_multiday_record
import pandas as pd
import json
import os
from datetime import datetime

def run_migration():
    print("[1/4] Supabase DB 전체 레코드 불러오는 중...")
    df = db_manager.fetch_all_work_logs()
    print(f"현재 DB 총 레코드: {len(df)}건")

    targets = []
    for _, r in df.iterrows():
        row_dict = r.to_dict()
        if is_multiday_record(row_dict):
            targets.append(row_dict)

    print(f"[2/4] 마이그레이션 대상 다일 레코드: {len(targets)}건")
    if not targets:
        print("마이그레이션 대상 레코드가 없습니다.")
        return

    # 안전 백업
    os.makedirs("data_backup", exist_ok=True)
    backup_file = f"data_backup/multidays_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump([
            {k: (str(v) if pd.notna(v) else None) for k, v in t.items()}
            for t in targets
        ], f, ensure_ascii=False, indent=2)
    print(f"안전 백업 완료: {backup_file}")

    print("[3/4] Supabase DB에 1일차 UPDATE 및 2일차 이후 INSERT 적용 중...")
    success_count = 0
    new_inserts_count = 0

    for idx, t in enumerate(targets, 1):
        target_id = t["id"]
        splits = split_multiday_record(t)
        
        # 1일차 -> UPDATE
        d1 = splits[0]
        update_payload = {
            "start_time": d1["start_time"],
            "end_time": d1["end_time"],
            "actual_minutes": int(d1["actual_minutes"]),
            "estimated_minutes": int(d1["estimated_minutes"]),
            "task_description": d1["task_description"],
            "status": "COMPLETED",
            "is_night_work": False,
            "is_weekend_work": bool(d1["is_weekend_work"]),
            "msg_hash": d1["msg_hash"]
        }
        db_manager.supabase.table("worktime_work_logs").update(update_payload).eq("id", target_id).execute()
        
        # 2일차 이후 -> INSERT
        for d_sub in splits[1:]:
            insert_payload = {
                "msg_hash": d_sub["msg_hash"],
                "log_type": d_sub.get("log_type") or "작업",
                "worker_name": d_sub.get("worker_name") or "",
                "worker_company": d_sub.get("worker_company") or "",
                "worker_title": d_sub.get("worker_title") or "",
                "worker_team": d_sub.get("worker_team") or "",
                "client_name": d_sub.get("client_name") or "",
                "task_description": d_sub.get("task_description") or "",
                "estimated_minutes": int(d_sub.get("estimated_minutes") or 540),
                "actual_minutes": int(d_sub.get("actual_minutes") or 540),
                "start_time": d_sub["start_time"],
                "end_time": d_sub["end_time"],
                "status": "COMPLETED",
                "is_night_work": False,
                "is_weekend_work": bool(d_sub["is_weekend_work"]),
                "raw_start_message": str(d_sub.get("raw_start_message") or ""),
                "raw_end_message": str(d_sub.get("raw_end_message") or "")
            }
            db_manager.supabase.table("worktime_work_logs").insert(insert_payload).execute()
            new_inserts_count += 1
            
        success_count += 1
        if idx % 10 == 0 or idx == len(targets):
            print(f"진행: {idx}/{len(targets)}건 완료 (신규 레코드 {new_inserts_count}건 추가)")

    print("[4/4] 마이그레이션 완료 후 무결성 검증 중...")
    # 로컬 캐시/SQLite와 동기화 위해 fetch_all_work_logs 호출
    df_after = db_manager.fetch_all_work_logs()
    print(f"마이그레이션 후 DB 총 레코드: {len(df_after)}건 (기존 {len(df)}건 -> {len(df_after)}건, 순증 {new_inserts_count}건)")
    
    # 김형일 수석 9월 1일, 2일 데이터 확인
    kh_9 = df_after[df_after["worker_name"].str.contains("김형일", na=False) & (df_after["start_time"].dt.month == 9)]
    print("\n--- [검증] 김형일 수석 9월 작업 내역 ---")
    for _, r in kh_9.iterrows():
        print(f"ID:{r['id']} | {r['worker_name']} | {r['client_name']} | {r['task_description']} | {r['start_time'].strftime('%Y-%m-%d %H:%M')} ~ {r['end_time'].strftime('%H:%M')} | {r['actual_hours']}h")

if __name__ == "__main__":
    run_migration()
