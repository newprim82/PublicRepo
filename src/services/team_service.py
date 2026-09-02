import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any
import pandas as pd

from ..config import config
from ..database.supabase_client import db_manager

DEFAULT_TEAMS = ["기술 1팀", "기술 2팀", "기술 3팀", "PI팀"]
DEFAULT_TITLES = ["사원", "대리", "과장", "수석"]
UNASSIGNED_TEAM = "미지정"

class TeamService:
    @staticmethod
    def init_team_table():
        """로컬 SQLite에 team_members 테이블 생성 및 컬럼 마이그레이션"""
        conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS team_members (
                worker_name TEXT PRIMARY KEY,
                team_name TEXT NOT NULL,
                job_title TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        
        # job_title 컬럼 존재 여부 체크 및 추가 (마이그레이션)
        cursor.execute("PRAGMA table_info(team_members)")
        cols = [c[1] for c in cursor.fetchall()]
        if "job_title" not in cols:
            cursor.execute("ALTER TABLE team_members ADD COLUMN job_title TEXT DEFAULT ''")

        conn.commit()
        conn.close()

    @staticmethod
    def get_team_members_info() -> Dict[str, Dict[str, str]]:
        """팀원별 소속팀 및 직급 딕셔너리 반환 { '김시우': {'team': '기술 1팀', 'title': '대리'}, ... }"""
        TeamService.init_team_table()
        info_map = {}

        # 1. Supabase 조회 시도
        if db_manager.use_supabase and db_manager.supabase:
            try:
                res = db_manager.supabase.table("worktime_team_members").select("*").execute()
                for row in (res.data or []):
                    info_map[row["worker_name"]] = {
                        "team": row.get("team_name") or UNASSIGNED_TEAM,
                        "title": row.get("job_title") or ""
                    }
                if info_map:
                    return info_map
            except Exception as e:
                print(f"[Supabase 팀원 조회 알림]: {e}")

        # 2. 로컬 SQLite 조회
        conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT worker_name, team_name, job_title FROM team_members")
        for w_name, t_name, j_title in cursor.fetchall():
            info_map[w_name] = {
                "team": t_name or UNASSIGNED_TEAM,
                "title": j_title or ""
            }
        conn.close()
        return info_map

    @staticmethod
    def get_team_mappings() -> Dict[str, str]:
        """팀원별 소속팀 딕셔너리 반환 { '김시우': '기술 1팀', ... }"""
        info_map = TeamService.get_team_members_info()
        return {w: data["team"] for w, data in info_map.items()}

    @staticmethod
    def get_title_mappings() -> Dict[str, str]:
        """팀원별 직급 딕셔너리 반환 { '김시우': '대리', ... }"""
        info_map = TeamService.get_team_members_info()
        return {w: data["title"] for w, data in info_map.items()}

    @staticmethod
    def save_worker_info(worker_name: str, team_name: str, job_title: str):
        """단일 팀원의 소속팀 및 직급을 저장하고 work_logs에도 즉시 동기화"""
        TeamService.init_team_table()
        target_team = UNASSIGNED_TEAM if "해제" in team_name or "미지정" in team_name else team_name.strip()
        target_title = job_title.strip()

        # 1. Supabase 저장
        if db_manager.use_supabase and db_manager.supabase:
            try:
                db_manager.supabase.table("worktime_team_members").upsert({
                    "worker_name": worker_name,
                    "team_name": target_team,
                    "job_title": target_title
                }).execute()
                db_manager.supabase.table("worktime_work_logs").update({
                    "worker_team": target_team,
                    "worker_title": target_title
                }).eq("worker_name", worker_name).execute()
            except Exception as e:
                print(f"[Supabase 팀원 저장 알림]: {e}")

        # 2. 로컬 SQLite 저장
        conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO team_members (worker_name, team_name, job_title, updated_at)
            VALUES (?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(worker_name) DO UPDATE SET
                team_name=excluded.team_name,
                job_title=excluded.job_title,
                updated_at=excluded.updated_at
        """, (worker_name, target_team, target_title))
        
        cursor.execute("UPDATE work_logs SET worker_team=?, worker_title=? WHERE worker_name=?", (target_team, target_title, worker_name))
        conn.commit()
        conn.close()

    @staticmethod
    def save_team_members(team_name: str, worker_names: List[str]):
        """특정 팀에 소속된 팀원 목록을 일괄 업데이트 (기존 직급 유지)"""
        TeamService.init_team_table()
        if not worker_names:
            return
            
        target_team = UNASSIGNED_TEAM if "해제" in team_name or "미지정" in team_name else team_name
        current_info = TeamService.get_team_members_info()

        for w_name in worker_names:
            existing_title = current_info.get(w_name, {}).get("title", "")
            TeamService.save_worker_info(w_name, target_team, existing_title)

    @staticmethod
    def update_worker_title(worker_name: str, job_title: str):
        """단일 팀원의 직급만 수정"""
        current_info = TeamService.get_team_members_info()
        team_name = current_info.get(worker_name, {}).get("team", UNASSIGNED_TEAM)
        TeamService.save_worker_info(worker_name, team_name, job_title)

    @staticmethod
    def remove_worker_team(worker_name: str):
        """단일 팀원의 소속 해제 (삭제)"""
        TeamService.save_team_members(UNASSIGNED_TEAM, [worker_name])

    @staticmethod
    def clear_team_all_members(team_name: str):
        """특정 팀에 소속된 모든 팀원의 소속을 일괄 해제"""
        mappings = TeamService.get_team_mappings()
        members = [w for w, t in mappings.items() if t == team_name]
        if members:
            TeamService.save_team_members(UNASSIGNED_TEAM, members)

    @staticmethod
    def auto_init_mappings_from_worklogs(all_workers: List[str], df_logs: pd.DataFrame):
        """기존 work_logs의 팀 및 직급 정보를 기반으로 초기 매핑 구성"""
        current_info = TeamService.get_team_members_info()
        unmapped = [w for w in all_workers if w not in current_info or not current_info[w].get("title")]
        
        if not unmapped or df_logs.empty:
            return

        for w in unmapped:
            worker_rows = df_logs[df_logs["worker_name"] == w]
            found_team = current_info.get(w, {}).get("team", "")
            found_title = current_info.get(w, {}).get("title", "")
            
            if not worker_rows.empty:
                if not found_team:
                    valid_teams = worker_rows["worker_team"].dropna().unique()
                    for t in valid_teams:
                        if t and t != UNASSIGNED_TEAM:
                            found_team = t
                            break
                            
                if not found_title:
                    valid_titles = worker_rows["worker_title"].dropna().unique()
                    for ti in valid_titles:
                        if ti:
                            found_title = ti
                            break
                            
            if (found_team and found_team != UNASSIGNED_TEAM) or found_title:
                TeamService.save_worker_info(w, found_team or UNASSIGNED_TEAM, found_title or "")
