import sys
import sqlite3
import pandas as pd
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import config
from src.database.supabase_client import db_manager

def sync_local_to_supabase():
    print("=" * 60)
    print("☁️ [Supabase 클라우드 데이터 일괄 동기화 마이그레이션 도구]")
    print("=" * 60)

    if not config.is_supabase_configured() or not db_manager.use_supabase:
        print("[!] Supabase 연결 정보가 설정되지 않았습니다.")
        print("💡 .env 파일에 SUPABASE_URL 과 SUPABASE_KEY 를 입력해주세요.")
        return

    # 1. 로컬 SQLite에서 최신 작업 로그 읽기
    conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
    df_logs = pd.read_sql_query("SELECT * FROM work_logs", conn)
    
    # 2. 로컬 팀원 정보 및 보상 휴가 읽기
    try:
        df_teams = pd.read_sql_query("SELECT * FROM team_members", conn)
    except Exception:
        df_teams = pd.DataFrame()
        
    try:
        df_rewards = pd.read_sql_query("SELECT * FROM reward_leave_logs", conn)
    except Exception:
        df_rewards = pd.DataFrame()
        
    conn.close()

    print(f"📊 로컬 SQLite 내역: 작업 로그 {len(df_logs)}건 / 팀원 정보 {len(df_teams)}명 / 보상 휴가 {len(df_rewards)}건")

    # 3. Supabase work_logs 일괄 Upsert
    if not df_logs.empty:
        payloads = []
        for idx, r in df_logs.iterrows():
            payloads.append({
                "msg_hash": r["msg_hash"],
                "log_type": r["log_type"],
                "worker_name": r["worker_name"],
                "worker_company": r["worker_company"],
                "worker_title": r["worker_title"],
                "worker_team": r["worker_team"],
                "client_name": r["client_name"],
                "task_description": r["task_description"],
                "estimated_minutes": int(r["estimated_minutes"]),
                "actual_minutes": int(r["actual_minutes"]),
                "start_time": r["start_time"],
                "end_time": r["end_time"] if pd.notna(r["end_time"]) else None,
                "status": r["status"],
                "is_night_work": bool(r["is_night_work"]),
                "is_weekend_work": bool(r["is_weekend_work"]),
                "raw_start_message": r["raw_start_message"],
                "raw_end_message": r["raw_end_message"]
            })

        batch_size = 100
        total_uploaded = 0
        for i in range(0, len(payloads), batch_size):
            batch = payloads[i:i+batch_size]
            db_manager.supabase.table("work_logs").upsert(batch, on_conflict="msg_hash").execute()
            total_uploaded += len(batch)
            print(f"  - [작업 로그 업로드 중...] {total_uploaded}/{len(payloads)}건 완료")

        print(f"🎉 [성공] 총 {total_uploaded}건의 작업 로그가 Supabase 클라우드에 완벽히 동기화되었습니다!")

    # 4. 팀원 정보 동기화
    if not df_teams.empty:
        team_payloads = []
        for idx, r in df_teams.iterrows():
            team_payloads.append({
                "worker_name": r["worker_name"],
                "team_name": r["team_name"],
                "job_title": r.get("job_title", "")
            })
        db_manager.supabase.table("team_members").upsert(team_payloads, on_conflict="worker_name").execute()
        print(f"👥 [성공] 총 {len(team_payloads)}명의 팀원 소속/직급 정보가 Supabase에 동기화되었습니다!")

    # 5. 보상 휴가 정보 동기화
    if not df_rewards.empty:
        reward_payloads = []
        for idx, r in df_rewards.iterrows():
            reward_payloads.append({
                "worker_name": r["worker_name"],
                "week_label": r["week_label"],
                "leave_hours": float(r["leave_hours"]),
                "note": r["note"]
            })
        db_manager.supabase.table("reward_leave_logs").upsert(reward_payloads).execute()
        print(f"🎁 [성공] 총 {len(reward_payloads)}건의 보상 휴가 기록이 Supabase에 동기화되었습니다!")

    print("\n✅ 모든 데이터가 Supabase 클라우드로 완벽히 이전되었습니다! 이제 모든 PC에서 실시간으로 공유됩니다.")

if __name__ == "__main__":
    sync_local_to_supabase()
