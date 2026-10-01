# -*- coding: utf-8 -*-
import os
import re
import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

from ..config import config


# 기본 등록 수신자
DEFAULT_RECIPIENTS = [
    {
        "email": "ymmoon@sangsanginworld.co.kr",
        "name": "문영민",
        "department": "기술본부",
        "schedule_cron": "매주 월요일 08:00",
        "include_cost": True,
        "is_active": True,
        "note": "기본 수신자 (주간 업무 실적 및 정산 보고서)",
        "created_at": "2026-09-01 08:00:00"
    }
]

DATA_DIR = config.BASE_DIR / "data"
LOCAL_JSON_PATH = DATA_DIR / "scheduled_email_recipients.json"


class EmailScheduleService:
    """
    📬 주기적(매주 월요일 오전 8시) 업무 실적 및 정산 리포트 메일 발송 대상 관리 서비스
    - 3중 영구 보존 엔진: Supabase Cloud DB + 로컬 SQLite + 로컬 JSON
    - 발송 대상자 추가, 수정, 활성화/비활성화, 삭제 및 검증
    """

    _cached_recipients: Optional[List[Dict[str, Any]]] = None

    @classmethod
    def _validate_email(cls, email: str) -> bool:
        if not email or not isinstance(email, str):
            return False
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        return bool(re.match(pattern, email.strip()))

    @classmethod
    def _init_sqlite_table(cls):
        try:
            db_path = config.LOCAL_DB_PATH
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_email_recipients (
                    email TEXT PRIMARY KEY,
                    name TEXT DEFAULT '',
                    department TEXT DEFAULT '',
                    schedule_cron TEXT DEFAULT '매주 월요일 08:00',
                    include_cost INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    note TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)
            conn.commit()
            conn.close()
        except Exception:
            pass

    @classmethod
    def _ensure_supabase_table(cls, client):
        try:
            client.table("worktime_scheduled_email_recipients").select("email").limit(1).execute()
        except Exception:
            pass

    @classmethod
    def get_all_recipients(cls, force_reload: bool = False) -> List[Dict[str, Any]]:
        """
        등록된 모든 정기 메일 수신자 목록 조회 (Supabase -> SQLite -> JSON 순으로 안전 동기화)
        """
        if cls._cached_recipients is not None and not force_reload:
            return cls._cached_recipients

        recipients_map: Dict[str, Dict[str, Any]] = {}

        # 0. 기본 내장 수신자 사전 탑재
        for dr in DEFAULT_RECIPIENTS:
            recipients_map[dr["email"].lower()] = dr.copy()

        # 1. Supabase Cloud DB 조회 시도
        loaded_from_cloud = False
        try:
            from ..database.supabase_client import db_manager
            client = getattr(db_manager, "supabase", None)
            if client:
                res = client.table("worktime_scheduled_email_recipients").select("*").execute()
                if res.data:
                    for r in res.data:
                        em = str(r.get("email", "")).lower().strip()
                        if em:
                            recipients_map[em] = {
                                "email": em,
                                "name": str(r.get("name", "")),
                                "department": str(r.get("department", "")),
                                "schedule_cron": str(r.get("schedule_cron", "매주 월요일 08:00")),
                                "include_cost": bool(r.get("include_cost", True)),
                                "is_active": bool(r.get("is_active", True)),
                                "note": str(r.get("note", "")),
                                "created_at": str(r.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                            }
                    loaded_from_cloud = True
        except Exception:
            loaded_from_cloud = False

        # 2. 로컬 SQLite 보강
        cls._init_sqlite_table()
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cur = conn.cursor()
            cur.execute("SELECT email, name, department, schedule_cron, include_cost, is_active, note, created_at FROM scheduled_email_recipients")
            rows = cur.fetchall()
            conn.close()
            for row in rows:
                em = str(row[0]).lower().strip()
                if em and (not loaded_from_cloud or em not in recipients_map):
                    recipients_map[em] = {
                        "email": em,
                        "name": str(row[1] or ""),
                        "department": str(row[2] or ""),
                        "schedule_cron": str(row[3] or "매주 월요일 08:00"),
                        "include_cost": bool(row[4]),
                        "is_active": bool(row[5]),
                        "note": str(row[6] or ""),
                        "created_at": str(row[7] or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    }
        except Exception:
            pass

        # 3. 로컬 JSON 보강
        if LOCAL_JSON_PATH.exists():
            try:
                with open(LOCAL_JSON_PATH, "r", encoding="utf-8") as f:
                    j_data = json.load(f)
                    if isinstance(j_data, list):
                        for item in j_data:
                            em = str(item.get("email", "")).lower().strip()
                            if em and em not in recipients_map:
                                recipients_map[em] = item
            except Exception:
                pass

        # 정렬: 기본 수신자 최상단, 이후 이메일 오름차순
        result = list(recipients_map.values())
        result.sort(key=lambda x: (0 if x["email"] == "ymmoon@sangsanginworld.co.kr" else 1, x["email"]))
        cls._cached_recipients = result

        # 로컬 파일 영구 보존 싱크
        cls._save_to_local_json(result)
        return result

    @classmethod
    def _save_to_local_json(cls, recipients: List[Dict[str, Any]]):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(LOCAL_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(recipients, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @classmethod
    def get_active_recipient_emails(cls) -> List[str]:
        """
        정기 자동 발송 배치(send_weekly_report.py) 실행 시 메일을 수신할 활성화된 이메일 목록 반환
        """
        all_rcpts = cls.get_all_recipients()
        active_emails = [r["email"] for r in all_rcpts if r.get("is_active", True)]
        if not active_emails:
            return ["ymmoon@sangsanginworld.co.kr"]
        return active_emails

    @classmethod
    def add_recipient(
        cls,
        email: str,
        name: str = "",
        department: str = "",
        schedule_cron: str = "매주 월요일 08:00",
        include_cost: bool = True,
        is_active: bool = True,
        note: str = ""
    ) -> Tuple[bool, str]:
        """
        신규 정기 발송 수신자 등록 (Supabase + SQLite + JSON 동시 반영)
        """
        clean_email = str(email).lower().strip()
        if not cls._validate_email(clean_email):
            return False, "유효한 이메일 형식(예: user@sangsanginworld.co.kr)이 아닙니다."

        recipients = cls.get_all_recipients(force_reload=True)
        for r in recipients:
            if r["email"].lower() == clean_email:
                return False, f"이미 등록되어 있는 이메일 주소입니다. ({clean_email})"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_item = {
            "email": clean_email,
            "name": name.strip(),
            "department": department.strip(),
            "schedule_cron": schedule_cron.strip() or "매주 월요일 08:00",
            "include_cost": bool(include_cost),
            "is_active": bool(is_active),
            "note": note.strip(),
            "created_at": now_str
        }

        # 1. Supabase 동기화
        try:
            from ..database.supabase_client import db_manager
            client = getattr(db_manager, "supabase", None)
            if client:
                client.table("worktime_scheduled_email_recipients").upsert([new_item]).execute()
        except Exception:
            pass

        # 2. 로컬 SQLite 동기화
        cls._init_sqlite_table()
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO scheduled_email_recipients (
                    email, name, department, schedule_cron, include_cost, is_active, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                clean_email, new_item["name"], new_item["department"],
                new_item["schedule_cron"], 1 if new_item["include_cost"] else 0,
                1 if new_item["is_active"] else 0, new_item["note"], now_str, now_str
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass

        # 3. 로컬 JSON 동기화 & 캐시 갱신
        recipients.append(new_item)
        recipients.sort(key=lambda x: (0 if x["email"] == "ymmoon@sangsanginworld.co.kr" else 1, x["email"]))
        cls._cached_recipients = recipients
        cls._save_to_local_json(recipients)

        # 4. AuthorizedRecipientService 화이트리스트에도 자동 등록
        try:
            from .authorized_recipient_service import AuthorizedRecipientService
            AuthorizedRecipientService.add_authorized_recipient(clean_email)
        except Exception:
            pass

        return True, f"'{clean_email}' 수신자가 성공적으로 등록되었습니다."

    @classmethod
    def update_recipient(
        cls,
        email: str,
        name: str,
        department: str,
        is_active: bool,
        include_cost: bool,
        note: str = ""
    ) -> Tuple[bool, str]:
        """
        등록된 수신자 정보 수정
        """
        clean_email = str(email).lower().strip()
        recipients = cls.get_all_recipients(force_reload=True)
        target = None
        for r in recipients:
            if r["email"].lower() == clean_email:
                target = r
                break

        if not target:
            return False, f"수신자 정보를 찾을 수 없습니다. ({clean_email})"

        target["name"] = name.strip()
        target["department"] = department.strip()
        target["is_active"] = bool(is_active)
        target["include_cost"] = bool(include_cost)
        target["note"] = note.strip()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Supabase 동기화
        try:
            from ..database.supabase_client import db_manager
            client = getattr(db_manager, "supabase", None)
            if client:
                client.table("worktime_scheduled_email_recipients").update({
                    "name": target["name"],
                    "department": target["department"],
                    "is_active": target["is_active"],
                    "include_cost": target["include_cost"],
                    "note": target["note"]
                }).eq("email", clean_email).execute()
        except Exception:
            pass

        # 2. 로컬 SQLite 동기화
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cur = conn.cursor()
            cur.execute("""
                UPDATE scheduled_email_recipients
                SET name = ?, department = ?, is_active = ?, include_cost = ?, note = ?, updated_at = ?
                WHERE email = ?
            """, (
                target["name"], target["department"], 1 if target["is_active"] else 0,
                1 if target["include_cost"] else 0, target["note"], now_str, clean_email
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass

        # 3. 로컬 JSON 동기화 & 캐시 갱신
        cls._cached_recipients = recipients
        cls._save_to_local_json(recipients)

        return True, f"'{clean_email}' 수신자 설정이 성공적으로 변경되었습니다."

    @classmethod
    def delete_recipient(cls, email: str) -> Tuple[bool, str]:
        """
        등록된 수신자 삭제 (기본 수신자는 삭제 불가)
        """
        clean_email = str(email).lower().strip()
        if clean_email == "ymmoon@sangsanginworld.co.kr":
            return False, "기본 수신자(ymmoon@sangsanginworld.co.kr)는 시스템 보호 대상이므로 삭제할 수 없습니다. 대신 '비활성화'로 전환하십시오."

        recipients = cls.get_all_recipients(force_reload=True)
        new_list = [r for r in recipients if r["email"].lower() != clean_email]
        if len(new_list) == len(recipients):
            return False, f"등록된 수신자를 찾을 수 없습니다. ({clean_email})"

        # 1. Supabase 동기화
        try:
            from ..database.supabase_client import db_manager
            client = getattr(db_manager, "supabase", None)
            if client:
                client.table("worktime_scheduled_email_recipients").delete().eq("email", clean_email).execute()
        except Exception:
            pass

        # 2. 로컬 SQLite 동기화
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cur = conn.cursor()
            cur.execute("DELETE FROM scheduled_email_recipients WHERE email = ?", (clean_email,))
            conn.commit()
            conn.close()
        except Exception:
            pass

        # 3. 로컬 JSON 동기화 & 캐시 갱신
        cls._cached_recipients = new_list
        cls._save_to_local_json(new_list)

        return True, f"'{clean_email}' 수신자가 발송 대상 목록에서 삭제되었습니다."

    @classmethod
    def toggle_active(cls, email: str) -> Tuple[bool, str]:
        """
        수신자 활성화/비활성화 토글
        """
        clean_email = str(email).lower().strip()
        recipients = cls.get_all_recipients(force_reload=True)
        target = None
        for r in recipients:
            if r["email"].lower() == clean_email:
                target = r
                break
        if not target:
            return False, "수신자를 찾을 수 없습니다."

        new_status = not target.get("is_active", True)
        return cls.update_recipient(
            email=clean_email,
            name=target.get("name", ""),
            department=target.get("department", ""),
            is_active=new_status,
            include_cost=target.get("include_cost", True),
            note=target.get("note", "")
        )
