import sys
import sqlite3
import pandas as pd
from pathlib import Path

# Windows 콘솔 cp949 유니코드 오류 방지
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import config
from src.database.supabase_client import db_manager

def sync_local_to_supabase():
    print("=" * 60)
    print("[Supabase Cloud DB Data Sync Migration Tool]")
    print("=" * 60)

    if not config.is_supabase_configured() or not db_manager.use_supabase:
        print("[!] Supabase is not configured or connection failed.")
        print("Please check SUPABASE_URL and SUPABASE_KEY in .env file.")
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

    print(f"Local SQLite: Work logs: {len(df_logs)} | Team members: {len(df_teams)} | Reward leaves: {len(df_rewards)}")

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
            try:
                db_manager.supabase.table("worktime_work_logs").upsert(batch, on_conflict="msg_hash").execute()
                total_uploaded += len(batch)
                print(f"  - [Uploading work logs...] {total_uploaded}/{len(payloads)} completed")
            except Exception as e:
                print(f"  - [Error during batch upload]: {e}")
                print("    (Please make sure you have executed supabase_schema.sql in Supabase SQL Editor!)")
                return

        print(f"[SUCCESS] Uploaded {total_uploaded} work logs to Supabase!")

    # 4. 팀원 정보 동기화
    if not df_teams.empty:
        team_payloads = []
        for idx, r in df_teams.iterrows():
            team_payloads.append({
                "worker_name": r["worker_name"],
                "team_name": r["team_name"],
                "job_title": r.get("job_title", "")
            })
        try:
            db_manager.supabase.table("worktime_team_members").upsert(team_payloads, on_conflict="worker_name").execute()
            print(f"[SUCCESS] Synchronized {len(team_payloads)} team members to Supabase!")
        except Exception as e:
            print(f"[Warning] Team members sync error: {e}")

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
        try:
            db_manager.supabase.table("worktime_reward_leave_logs").upsert(reward_payloads).execute()
            print(f"[SUCCESS] Synchronized {len(reward_payloads)} reward leaves to Supabase!")
        except Exception as e:
            print(f"[Warning] Reward leaves sync error: {e}")

    print("\n[SUCCESS] All data has been synchronized to Supabase Cloud DB!")

if __name__ == "__main__":
    sync_local_to_supabase()
