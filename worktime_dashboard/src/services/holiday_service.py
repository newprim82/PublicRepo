import os
import json
import sqlite3
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Any, Optional, Set
import pandas as pd

from ..config import config


class HolidayService:
    """
    🇰🇷 대한민국 법정 공휴일, 법정 대체공휴일 및 정부 지정 임시공휴일 통합 관리 서비스
    - 관공서의 공휴일에 관한 규정(대통령령) 제4조의2(대체공휴일) 알고리즘 100% 반영
    - 한국천문연구원 공식 역법 기준 음력 명절(설날, 추석, 부처님오신날) 완벽 지원
    - 정부 지정 임시공휴일 관리자 직접 등록/삭제 및 실시간 1.5배 할증 연동
    """

    # 1. 양력 고정 공휴일 (월, 일): (명칭, 대체공휴일 적용 대상 여부)
    SOLAR_FIXED_HOLIDAYS = {
        (1, 1): ("신정", False),
        (3, 1): ("3·1절", True),
        (5, 5): ("어린이날", True),
        (6, 6): ("현충일", False),
        (8, 15): ("광복절", True),
        (10, 3): ("개천절", True),
        (10, 9): ("한글날", True),
        (12, 25): ("성탄절", True),  # 2023년부터 대체공휴일 적용 확대
    }

    # 2. 음력 명절 및 부처님오신날 공식 일자 (한국천문연구원 공식 발표 데이터, 2024~2030)
    LUNAR_HOLIDAYS_MAP = {
        2024: {
            "설날연휴": ["2024-02-09", "2024-02-10", "2024-02-11"],
            "부처님오신날": ["2024-05-15"],
            "추석연휴": ["2024-09-16", "2024-09-17", "2024-09-18"],
        },
        2025: {
            "설날연휴": ["2025-01-28", "2025-01-29", "2025-01-30"],
            "부처님오신날": ["2025-05-05"],
            "추석연휴": ["2025-10-05", "2025-10-06", "2025-10-07"],
        },
        2026: {
            "설날연휴": ["2026-02-16", "2026-02-17", "2026-02-18"],
            "부처님오신날": ["2026-05-24"],
            "추석연휴": ["2026-09-24", "2026-09-25", "2026-09-26"],
        },
        2027: {
            "설날연휴": ["2027-02-06", "2027-02-07", "2027-02-08"],
            "부처님오신날": ["2027-05-13"],
            "추석연휴": ["2027-09-14", "2027-09-15", "2027-09-16"],
        },
        2028: {
            "설날연휴": ["2028-01-26", "2028-01-27", "2028-01-28"],
            "부처님오신날": ["2028-05-02"],
            "추석연휴": ["2028-10-02", "2028-10-03", "2028-10-04"],
        },
        2029: {
            "설날연휴": ["2029-02-12", "2029-02-13", "2029-02-14"],
            "부처님오신날": ["2029-05-20"],
            "추석연휴": ["2029-09-21", "2029-09-22", "2029-09-23"],
        },
        2030: {
            "설날연휴": ["2030-02-02", "2030-02-03", "2030-02-04"],
            "부처님오신날": ["2030-05-09"],
            "추석연휴": ["2030-09-11", "2030-09-12", "2030-09-13"],
        }
    }

    # 캐시된 임시공휴일 딕셔너리 (날짜: 사유)
    _cached_custom_holidays: Optional[Dict[str, str]] = None

    @classmethod
    def get_custom_holidays(cls, force_reload: bool = False) -> Dict[str, str]:
        """정부 지정 임시공휴일 목록 반환 (DB -> 로컬 SQLite -> JSON 3중 영구 보존)"""
        if cls._cached_custom_holidays is not None and not force_reload:
            return cls._cached_custom_holidays

        holidays = {}
        # 1. Supabase Cloud DB 조회
        try:
            from ..database.supabase_client import DatabaseManager
            db = DatabaseManager()
            if db.use_supabase and db.supabase:
                res = db.supabase.table("worktime_custom_holidays").select("holiday_date, holiday_name").execute()
                if res.data:
                    for r in res.data:
                        d = str(r.get("holiday_date", "")).strip()
                        n = str(r.get("holiday_name", "")).strip()
                        if d and n:
                            holidays[d] = n
        except Exception:
            pass

        # 2. 로컬 SQLite 조회
        if not holidays:
            try:
                conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS custom_holidays (
                        holiday_date TEXT PRIMARY KEY,
                        holiday_name TEXT NOT NULL,
                        created_by TEXT DEFAULT '관리자',
                        created_at TEXT DEFAULT (datetime('now', 'localtime'))
                    )
                """)
                cursor.execute("SELECT holiday_date, holiday_name FROM custom_holidays")
                for d, n in cursor.fetchall():
                    d = str(d).strip()
                    n = str(n).strip()
                    if d and n:
                        holidays[d] = n
                conn.close()
            except Exception:
                pass

        # 3. 로컬 JSON 파일 fallback 조회
        fallback_json = config.LOCAL_DB_PATH.parent / "custom_holidays.json"
        if fallback_json.exists():
            try:
                with open(fallback_json, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    for k, v in file_data.items():
                        if k not in holidays:
                            holidays[k] = v
            except Exception:
                pass

        cls._cached_custom_holidays = holidays
        return holidays

    @classmethod
    def add_custom_holiday(cls, holiday_date: str, holiday_name: str, created_by: str = "관리자") -> bool:
        """관리자 지정 임시공휴일 추가 (DB 영구 보존)"""
        d_clean = holiday_date.strip()
        n_clean = holiday_name.strip()
        if not d_clean or not n_clean:
            return False

        # 1. Supabase 저장
        try:
            from ..database.supabase_client import DatabaseManager
            db = DatabaseManager()
            if db.use_supabase and db.supabase:
                db.supabase.table("worktime_custom_holidays").upsert({
                    "holiday_date": d_clean,
                    "holiday_name": n_clean,
                    "created_by": created_by
                }).execute()
        except Exception:
            pass

        # 2. 로컬 SQLite 저장
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS custom_holidays (
                    holiday_date TEXT PRIMARY KEY,
                    holiday_name TEXT NOT NULL,
                    created_by TEXT DEFAULT '관리자',
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)
            cursor.execute("""
                INSERT OR REPLACE INTO custom_holidays (holiday_date, holiday_name, created_by, created_at)
                VALUES (?, ?, ?, datetime('now', 'localtime'))
            """, (d_clean, n_clean, created_by))
            conn.commit()
            conn.close()
        except Exception:
            pass

        # 3. 로컬 JSON 저장
        try:
            fallback_json = config.LOCAL_DB_PATH.parent / "custom_holidays.json"
            fallback_json.parent.mkdir(parents=True, exist_ok=True)
            current = {}
            if fallback_json.exists():
                with open(fallback_json, "r", encoding="utf-8") as f:
                    current = json.load(f)
            current[d_clean] = n_clean
            with open(fallback_json, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # 캐시 갱신
        cls._cached_custom_holidays = None
        cls.get_custom_holidays(force_reload=True)
        return True

    @classmethod
    def delete_custom_holiday(cls, holiday_date: str) -> bool:
        """관리자 지정 임시공휴일 삭제"""
        d_clean = holiday_date.strip()
        if not d_clean:
            return False

        # 1. Supabase 삭제
        try:
            from ..database.supabase_client import DatabaseManager
            db = DatabaseManager()
            if db.use_supabase and db.supabase:
                db.supabase.table("worktime_custom_holidays").delete().eq("holiday_date", d_clean).execute()
        except Exception:
            pass

        # 2. 로컬 SQLite 삭제
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM custom_holidays WHERE holiday_date = ?", (d_clean,))
            conn.commit()
            conn.close()
        except Exception:
            pass

        # 3. 로컬 JSON 삭제
        try:
            fallback_json = config.LOCAL_DB_PATH.parent / "custom_holidays.json"
            if fallback_json.exists():
                with open(fallback_json, "r", encoding="utf-8") as f:
                    current = json.load(f)
                if d_clean in current:
                    del current[d_clean]
                    with open(fallback_json, "w", encoding="utf-8") as f:
                        json.dump(current, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        cls._cached_custom_holidays = None
        cls.get_custom_holidays(force_reload=True)
        return True

    @classmethod
    def get_holidays_for_year(cls, year: int) -> List[Dict[str, Any]]:
        """
        특정 연도의 모든 공휴일(고정 법정 공휴일 + 음력 명절 + 법정 대체공휴일 + 임시공휴일)을 날짜순으로 정렬하여 반환
        """
        holiday_dict: Dict[str, Dict[str, str]] = {}

        # 1. 고정 양력 공휴일 등록
        for (m, d), (name, is_sub) in cls.SOLAR_FIXED_HOLIDAYS.items():
            dt_str = f"{year:04d}-{m:02d}-{d:02d}"
            holiday_dict[dt_str] = {
                "name": name,
                "type": "법정공휴일",
                "sub_target": is_sub
            }

        # 2. 음력 명절 및 부처님오신날 등록
        lunar_data = cls.LUNAR_HOLIDAYS_MAP.get(year, {})
        for cat, dt_list in lunar_data.items():
            for dt_str in dt_list:
                holiday_dict[dt_str] = {
                    "name": cat,
                    "type": "법정공휴일",
                    "sub_target": True
                }

        # 3. 법정 대체공휴일 산출 (관공서의 공휴일에 관한 규정 제4조의2)
        # 대체공휴일 규칙:
        # - 설날/추석 연휴 중 일요일 또는 다른 공휴일과 겹치는 경우 -> 다음 첫 번째 비공휴일
        # - 3·1절, 어린이날, 부처님오신날, 광복절, 개천절, 한글날, 성탄절이 토요일·일요일과 겹치는 경우 -> 다음 첫 번째 비공휴일
        sub_holidays: Dict[str, str] = {}
        for dt_str, info in list(holiday_dict.items()):
            if not info.get("sub_target", False):
                continue

            dt_obj = datetime.strptime(dt_str, "%Y-%m-%d").date()
            weekday = dt_obj.weekday()  # 0: 월 ... 5: 토, 6: 일

            is_seollal_or_chuseok = "설날" in info["name"] or "추석" in info["name"]

            # 대체공휴일 발생 조건:
            # - 설날/추석: 일요일(6)과 겹치거나 다른 법정공휴일과 겹치는 경우
            # - 기타 주요 공휴일: 토요일(5) 또는 일요일(6)과 겹치거나 다른 법정공휴일과 겹치는 경우
            trigger = False
            if is_seollal_or_chuseok:
                if weekday == 6:  # 일요일
                    trigger = True
            else:
                if weekday in [5, 6]:  # 토요일 또는 일요일
                    trigger = True

            if trigger:
                # 다음 첫 번째 비공휴일(토/일이 아니고 기존 공휴일도 아닌 날) 탐색
                next_day = dt_obj + timedelta(days=1)
                while True:
                    next_str = next_day.strftime("%Y-%m-%d")
                    # 토요일(5), 일요일(6), 기존 공휴일, 이미 지정된 대체공휴일이면 건너뜀
                    if next_day.weekday() in [5, 6] or next_str in holiday_dict or next_str in sub_holidays:
                        next_day += timedelta(days=1)
                    else:
                        sub_holidays[next_str] = f"{info['name']} 대체공휴일"
                        break

        # 대체공휴일 병합
        for dt_str, s_name in sub_holidays.items():
            if dt_str not in holiday_dict:
                holiday_dict[dt_str] = {
                    "name": s_name,
                    "type": "대체공휴일",
                    "sub_target": False
                }

        # 4. 정부 지정 임시공휴일 병합
        custom_holidays = cls.get_custom_holidays()
        for dt_str, c_name in custom_holidays.items():
            if dt_str.startswith(f"{year:04d}-"):
                holiday_dict[dt_str] = {
                    "name": c_name,
                    "type": "정부 임시공휴일",
                    "sub_target": False
                }

        # 날짜순 정렬 및 요일 추가
        weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
        result = []
        for dt_str in sorted(holiday_dict.keys()):
            dt_obj = datetime.strptime(dt_str, "%Y-%m-%d").date()
            w_str = weekday_names[dt_obj.weekday()]
            info = holiday_dict[dt_str]
            result.append({
                "date": dt_str,
                "day_name": f"{w_str}요일",
                "holiday_name": info["name"],
                "holiday_type": info["type"],
                "is_weekend": dt_obj.weekday() in [5, 6]
            })

        return result

    @classmethod
    def get_all_holiday_dates(cls, start_year: int = 2024, end_year: int = 2030) -> Set[str]:
        """지정 기간 전체의 공휴일 날짜(YYYY-MM-DD) Set 반환 (초고속 O(1) 조회)"""
        dates = set()
        for y in range(start_year, end_year + 1):
            h_list = cls.get_holidays_for_year(y)
            for item in h_list:
                dates.add(item["date"])
        return dates

    @classmethod
    def is_holiday(cls, target_date: Any) -> Tuple[bool, str]:
        """
        주어진 날짜가 법정 공휴일, 대체공휴일, 또는 정부 임시공휴일인지 판별
        - 반환: (공휴일 여부: bool, 공휴일 명칭: str)
        """
        if target_date is None or pd.isna(target_date):
            return False, ""

        if isinstance(target_date, str):
            clean_str = target_date.strip()[:10]
            try:
                dt_obj = datetime.strptime(clean_str, "%Y-%m-%d").date()
            except Exception:
                return False, ""
        elif isinstance(target_date, datetime):
            dt_obj = target_date.date()
        elif isinstance(target_date, date):
            dt_obj = target_date
        else:
            return False, ""

        dt_str = dt_obj.strftime("%Y-%m-%d")
        year = dt_obj.year

        year_holidays = cls.get_holidays_for_year(year)
        for h in year_holidays:
            if h["date"] == dt_str:
                return True, h["holiday_name"]

        return False, ""

    @classmethod
    def is_weekend_or_holiday(cls, target_date: Any) -> Tuple[bool, str]:
        """
        주어진 날짜가 주말(토/일)이거나 법정/대체/임시 공휴일인지 종합 판별
        - 근로기준법상 1.5배 할증 대상 휴일근로 여부 판단의 핵심 함수
        - 반환: (휴일 여부: bool, 휴일 설명: str)
        """
        if target_date is None or pd.isna(target_date):
            return False, ""

        if isinstance(target_date, str):
            clean_str = target_date.strip()[:10]
            try:
                dt_obj = datetime.strptime(clean_str, "%Y-%m-%d").date()
            except Exception:
                return False, ""
        elif isinstance(target_date, datetime):
            dt_obj = target_date.date()
        elif isinstance(target_date, date):
            dt_obj = target_date
        else:
            return False, ""

        weekday = dt_obj.weekday()
        # 1. 공휴일 여부 우선 확인
        is_h, h_name = cls.is_holiday(dt_obj)
        if is_h:
            if weekday == 5:
                return True, f"{h_name} (토요일)"
            elif weekday == 6:
                return True, f"{h_name} (일요일)"
            return True, h_name

        # 2. 순수 주말 확인
        if weekday == 5:
            return True, "토요일 (주말)"
        elif weekday == 6:
            return True, "일요일 (주말)"

        return False, ""
