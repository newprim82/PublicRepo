import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from ..config import config
from ..database.supabase_client import db_manager

KST = timezone(timedelta(hours=9))

class CollectorStatusService:
    """
    카카오톡 자동 수집기의 실시간 가동 상태(정상/로그인필요/창닫힘/장애)를
    Supabase 클라우드 DB 및 로컬 캐시에 동기화하여 대시보드 화면에 장애 경보를 표출하는 서비스
    """
    STATUS_RECORD_KEY = "SYS_STATUS_COLLECTOR"
    LOCAL_CACHE_FILE = config.BASE_DIR / "collector_status.json"

    @classmethod
    def report_status(cls, status_code: str, message: str, total_records: int = 0, saved_records: int = 0):
        """
        수집기 PC에서 매 수집 시도 결과(정상/로그인필요/창미열림/에러)를 클라우드 및 로컬에 실시간 기록
        """
        try:
            now_kst = datetime.now(timezone.utc).astimezone(KST)
            now_str = now_kst.strftime("%Y-%m-%d %H:%M:%S")
            
            is_healthy = (status_code in ["ONLINE", "SUCCESS", "NO_NEW_RECORDS"])
            
            payload = {
                "is_healthy": is_healthy,
                "status_code": status_code,
                "message": message,
                "total_records": total_records,
                "saved_records": saved_records,
                "updated_at": now_str
            }
            
            # 1. 로컬 JSON 캐시 저장
            try:
                cls.LOCAL_CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

            # 2. Supabase 클라우드 DB 기록 (worktime_team_members 특수 시스템 레코드 활용, varchar(50) 준수)
            if db_manager.use_supabase and db_manager.supabase:
                try:
                    # team_name, job_title 컬럼 길이 50자 제한 준수
                    short_code = status_code[:30]
                    # 시각(16자) + "|" + 간략사유(최대 30자)
                    short_msg = message.replace("\n", " ").strip()
                    compact_job_title = f"{now_str[:16]}|{short_msg}"[:50]
                    
                    db_manager.supabase.table("worktime_team_members").upsert({
                        "worker_name": cls.STATUS_RECORD_KEY,
                        "team_name": short_code,
                        "job_title": compact_job_title
                    }, on_conflict="worker_name").execute()
                except Exception as e:
                    print(f"[수집기 상태 클라우드 동기화 알림]: {e}")
        except Exception as ex:
            print(f"[CollectorStatusService.report_status 예외]: {ex}")

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """
        대시보드에서 수집기 현재 상태를 실시간 조회 (클라우드 최우선 -> 로컬 파일 -> 기본값)
        """
        # 1. Supabase 클라우드 조회
        if db_manager.use_supabase and db_manager.supabase:
            try:
                res = db_manager.supabase.table("worktime_team_members")\
                    .select("*")\
                    .eq("worker_name", cls.STATUS_RECORD_KEY)\
                    .limit(1)\
                    .execute()
                if res.data:
                    row = res.data[0]
                    status_code = row.get("team_name", "UNKNOWN")
                    raw_title = str(row.get("job_title", "") or "")
                    
                    updated_at = ""
                    message = "카카오톡 PC 로그인이 풀려있거나 대화방 창이 닫혀 있습니다."
                    if "|" in raw_title:
                        parts = raw_title.split("|", 1)
                        updated_at = parts[0].strip()
                        if len(parts) > 1 and parts[1].strip():
                            message = parts[1].strip()
                    elif raw_title:
                        message = raw_title
                        
                    is_healthy = (status_code in ["ONLINE", "SUCCESS", "NO_NEW_RECORDS"])
                    return {
                        "is_healthy": is_healthy,
                        "status_code": status_code,
                        "message": message,
                        "updated_at": updated_at
                    }
            except Exception:
                pass

        # 2. 로컬 JSON 파일 조회
        if cls.LOCAL_CACHE_FILE.exists():
            try:
                content = cls.LOCAL_CACHE_FILE.read_text(encoding="utf-8")
                return json.loads(content)
            except Exception:
                pass

        # 3. 기본값 (알 수 없음)
        return {
            "is_healthy": False,
            "status_code": "LOGIN_REQUIRED_OR_WINDOW_CLOSED",
            "message": "카카오톡 PC 로그인이 풀려있거나 대화방 창이 닫혀 있습니다.",
            "updated_at": datetime.now(timezone.utc).astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
        }

