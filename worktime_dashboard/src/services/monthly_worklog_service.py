# -*- coding: utf-8 -*-
import io
import re
import json
import sqlite3
import smtplib
import base64
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import make_msgid, formatdate
from email.header import Header

import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from ..config import config
from ..database.supabase_client import db_manager
from .schedule_sync_service import ScheduleSyncService
from .team_service import TeamService
from .email_dispatch_service import EmailDispatchService
from ..dashboard.common.ui_helpers import get_current_kst_time, strip_tz


DATA_DIR = config.BASE_DIR / "data"
LOCAL_CONFIG_JSON = DATA_DIR / "team_monthly_email_config.json"

DEFAULT_TEAM_CONFIGS = {
    "기술 1팀": {
        "team_name": "기술 1팀",
        "team_email": "GE101@sangsanginworld.co.kr",
        "schedule_cron": "매달 1일 08:00",
        "is_active": True,
        "note": "기술 1팀 전월 업무 원장(카톡/아웃룩) 정기 발송",
        "updated_at": "2026-10-01 08:00:00"
    }
}


class MonthlyWorklogService:
    """
    📑 팀별 전월 업무 원장(카톡/아웃룩) 엑셀 정기 발송 서비스
    - 매달 1일 전월 실적 전체를 엑셀 다중 시트로 자동 생성
    - 지정된 팀 대표 이메일(예: GE101@sangsanginworld.co.kr)로 정기 전달
    - 즉시 테스트 발송 및 브라우저 엑셀 다운로드 지원
    """

    _cached_configs: Optional[Dict[str, Dict[str, Any]]] = None

    @classmethod
    def get_previous_month(cls, base_dt: Optional[datetime] = None) -> str:
        """기준일(기본: KST 현재 시각) 기준 전월 'YYYY-MM' 문자열 반환"""
        if base_dt is None:
            base_dt = get_current_kst_time()
        
        # 1일의 전날 -> 지난달 마지막 날
        first_day_of_current = base_dt.replace(day=1)
        last_day_of_prev = first_day_of_current - pd.Timedelta(days=1)
        return last_day_of_prev.strftime("%Y-%m")

    # =========================================================
    # 1. 팀 설정 관리 (SQLite + JSON 하이브리드 영구 저장)
    # =========================================================
    @classmethod
    def _init_sqlite_table(cls):
        try:
            db_path = config.LOCAL_DB_PATH
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS team_monthly_email_configs (
                    team_name TEXT PRIMARY KEY,
                    team_email TEXT NOT NULL,
                    schedule_cron TEXT DEFAULT '매달 1일 08:00',
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
    def get_all_team_configs(cls, force_reload: bool = False) -> Dict[str, Dict[str, Any]]:
        if cls._cached_configs is not None and not force_reload:
            return cls._cached_configs

        configs = {k: v.copy() for k, v in DEFAULT_TEAM_CONFIGS.items()}

        # 1. 로컬 SQLite에서 로드
        cls._init_sqlite_table()
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM team_monthly_email_configs")
            for r in cur.fetchall():
                row_dict = dict(r)
                team_name = row_dict.get("team_name", "").strip()
                if team_name:
                    configs[team_name] = {
                        "team_name": team_name,
                        "team_email": row_dict.get("team_email", ""),
                        "schedule_cron": row_dict.get("schedule_cron", "매달 1일 08:00"),
                        "is_active": bool(row_dict.get("is_active", 1)),
                        "note": row_dict.get("note", ""),
                        "updated_at": row_dict.get("updated_at", "")
                    }
            conn.close()
        except Exception:
            pass

        # 2. 로컬 JSON fallback
        try:
            if LOCAL_CONFIG_JSON.exists():
                with open(LOCAL_CONFIG_JSON, "r", encoding="utf-8") as f:
                    file_configs = json.load(f)
                    if isinstance(file_configs, dict):
                        for k, v in file_configs.items():
                            configs[k] = v
        except Exception:
            pass

        cls._cached_configs = configs
        return configs

    @classmethod
    def get_team_config(cls, team_name: str) -> Dict[str, Any]:
        configs = cls.get_all_team_configs()
        # 공백 제거 유연한 매칭 ("기술 1팀" == "기술1팀")
        clean_target = team_name.replace(" ", "")
        for t_name, cfg in configs.items():
            if t_name.replace(" ", "") == clean_target:
                return cfg
        
        # 기본값 생성
        return {
            "team_name": team_name,
            "team_email": "GE101@sangsanginworld.co.kr" if "1" in team_name else f"{clean_target.lower()}@sangsanginworld.co.kr",
            "schedule_cron": "매달 1일 08:00",
            "is_active": True,
            "note": f"{team_name} 전월 업무 원장 정기 발송",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    @classmethod
    def save_team_config(cls, team_name: str, team_email: str, is_active: bool = True, note: str = "") -> bool:
        cls._init_sqlite_table()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        clean_email = team_email.strip()
        # 1. SQLite 저장
        try:
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO team_monthly_email_configs (team_name, team_email, is_active, note, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(team_name) DO UPDATE SET
                    team_email = excluded.team_email,
                    is_active = excluded.is_active,
                    note = excluded.note,
                    updated_at = excluded.updated_at
            """, (team_name, clean_email, 1 if is_active else 0, note, now_str))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[MonthlyWorklogService] SQLite 설정 저장 오류: {e}")

        # 2. 로컬 JSON 저장
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            configs = cls.get_all_team_configs(force_reload=True)
            configs[team_name] = {
                "team_name": team_name,
                "team_email": clean_email,
                "schedule_cron": "매달 1일 08:00",
                "is_active": is_active,
                "note": note,
                "updated_at": now_str
            }
            with open(LOCAL_CONFIG_JSON, "w", encoding="utf-8") as f:
                json.dump(configs, f, ensure_ascii=False, indent=2)
            cls._cached_configs = configs
        except Exception:
            pass

        return True

    # =========================================================
    # 2. 전월 데이터 추출 및 정제
    # =========================================================
    @classmethod
    def get_team_monthly_data(cls, team_name: str, month_str: str) -> pd.DataFrame:
        """
        특정 팀의 특정 월(전월) 카톡 + 아웃룩 통합 데이터 조회
        """
        df_raw = db_manager.fetch_all_work_logs()
        if df_raw.empty:
            return pd.DataFrame()

        # 아웃룩 일정 결합
        try:
            df = ScheduleSyncService.combine_all_work_logs(df_raw)
        except Exception:
            df = df_raw.copy()

        # 팀원 매핑 확인
        team_mappings = TeamService.get_team_mappings()
        clean_team = team_name.replace(" ", "")
        
        # 해당 팀 소속 팀원 필터링
        team_workers = [
            w for w, t in team_mappings.items() 
            if str(t).replace(" ", "") == clean_team
        ]
        
        # 팀 컬럼에서도 매칭 확인
        mask = (df["month_str"] == month_str)
        if team_workers:
            mask = mask & (df["worker_name"].isin(team_workers) | (df["worker_team"].str.replace(" ", "") == clean_team))
        else:
            mask = mask & (df["worker_team"].str.replace(" ", "") == clean_team)

        team_df = df[mask].copy()
        if team_df.empty:
            return team_df

        # 최신 직급 매핑
        title_map = TeamService.get_title_mappings()
        team_df["worker_title"] = team_df["worker_name"].map(title_map).fillna(team_df.get("worker_title", ""))

        # is_outlook 정규화
        if "is_outlook" in team_df.columns:
            team_df["is_outlook"] = team_df["is_outlook"].fillna(False).astype(bool)
        else:
            team_df["is_outlook"] = False

        # 일자순 정렬
        if "start_time" in team_df.columns:
            team_df["start_time"] = pd.to_datetime(team_df["start_time"], errors="coerce")
            team_df = team_df.sort_values(by=["start_time", "worker_name"], ascending=[True, True])

        return team_df

    # =========================================================
    # 3. 고품질 다중 시트 Excel 원장 생성 (Cisco ACI 테마)
    # =========================================================
    @classmethod
    def generate_monthly_worklog_excel(cls, df: pd.DataFrame, team_name: str, month_str: str) -> bytes:
        """
        기술1팀 인원 전체에 대한 전월 카톡/아웃룩 엑셀 원장 파일 생성
        다중 시트:
          1. 요약 현황: 팀 총괄 KPI, 팀원별 실적 비교표(카톡 건수/공수, 아웃룩 일정 건수/공수, 총 합계)
          2. 카카오톡 업무 원장: 카카오톡 기반 실제 업무 지원 전체 내역
          3. 아웃룩 캘린더 원장: 아웃룩 일정(회의/외근/연차 등) 전체 내역
          4. 전체 통합 원장: 카톡 + 아웃룩 일체 통합 상세 장표
        """
        wb = openpyxl.Workbook()
        default_sheet = wb.active

        # 컬러 팔레트 & 폰트 정의
        navy_dark = "002D42"   # 주요 테이블 헤더
        navy_sub = "0284C7"    # 서브 헤더 (시안 블루)
        gray_zebra = "F8FAFC"  # 짝수행 은은한 배경
        white = "FFFFFF"
        total_bg = "E2E8F0"    # 합계 행 배경
        border_light = Side(border_style="thin", color="CBD5E1")
        cell_border = Border(left=border_light, right=border_light, top=border_light, bottom=border_light)
        total_top_border = Border(left=border_light, right=border_light, top=Side(border_style="medium", color="002D42"), bottom=Side(border_style="double", color="002D42"))

        font_main_title = Font(name="맑은 고딕", size=15, bold=True, color="002D42")
        font_sub_title = Font(name="맑은 고딕", size=10, color="64748B")
        font_sec_header = Font(name="맑은 고딕", size=11, bold=True, color="002D42")
        font_th = Font(name="맑은 고딕", size=10.5, bold=True, color="FFFFFF")
        font_td = Font(name="맑은 고딕", size=10)
        font_td_bold = Font(name="맑은 고딕", size=10, bold=True)
        font_total = Font(name="맑은 고딕", size=10.5, bold=True, color="002D42")

        fill_th_main = PatternFill(start_color=navy_dark, end_color=navy_dark, fill_type="solid")
        fill_th_sub = PatternFill(start_color=navy_sub, end_color=navy_sub, fill_type="solid")
        fill_zebra = PatternFill(start_color=gray_zebra, end_color=gray_zebra, fill_type="solid")
        fill_white = PatternFill(start_color=white, end_color=white, fill_type="solid")
        fill_tot = PatternFill(start_color=total_bg, end_color=total_bg, fill_type="solid")

        align_center = Alignment(horizontal="center", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        data = df.copy()
        if not data.empty:
            for col in ["start_time", "end_time"]:
                if col in data.columns:
                    data[col] = pd.to_datetime(data[col], errors="coerce")

        # ---------------------------------------------------------
        # Sheet 1: 요약 현황 (Summary)
        # ---------------------------------------------------------
        ws1 = wb.create_sheet(title="요약 현황")
        ws1.views.sheetView[0].showGridLines = True

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        ws1["A1"] = f"📊 {team_name} {month_str} 전월 업무 실적 및 원장 총괄 요약"
        ws1["A1"].font = font_main_title
        ws1["A2"] = f"출력 일시: {now_str} | 대상 팀: {team_name} | 대상 기간: {month_str}"
        ws1["A2"].font = font_sub_title

        # 총괄 KPI 산출
        tot_records = len(data)
        kakao_df = data[~data["is_outlook"]] if "is_outlook" in data.columns else data
        outlook_df = data[data["is_outlook"]] if "is_outlook" in data.columns else pd.DataFrame()

        tot_actual_hours = round(data["actual_hours"].sum(), 1) if "actual_hours" in data.columns else 0.0
        kakao_hours = round(kakao_df["actual_hours"].sum(), 1) if "actual_hours" in kakao_df.columns else 0.0
        outlook_hours = round(outlook_df["actual_hours"].sum(), 1) if not outlook_df.empty and "actual_hours" in outlook_df.columns else 0.0
        tot_workers = data["worker_name"].nunique() if "worker_name" in data.columns else 0
        tot_clients = kakao_df["client_name"].nunique() if not kakao_df.empty and "client_name" in kakao_df.columns else 0
        night_hours = round(data[data.get("is_night_work") == True]["actual_hours"].sum(), 1) if "actual_hours" in data.columns and "is_night_work" in data.columns else 0.0
        weekend_hours = round(data[data.get("is_weekend_work") == True]["actual_hours"].sum(), 1) if "actual_hours" in data.columns and "is_weekend_work" in data.columns else 0.0

        # KPI 테이블 (A4:B10)
        ws1["A4"] = "📌 핵심 관리 지표"
        ws1["B4"] = "실적 수치"
        for col_letter in ["A", "B"]:
            ws1[f"{col_letter}4"].font = font_th
            ws1[f"{col_letter}4"].fill = fill_th_main
            ws1[f"{col_letter}4"].alignment = align_center

        kpis = [
            ("총 투입 공수", f"{tot_actual_hours:,.1f} 시간"),
            ("총 업무/일정 건수", f"{tot_records:,} 건 (카카오톡: {len(kakao_df):,}건 / 아웃룩: {len(outlook_df):,}건)"),
            ("카카오톡 업무 공수", f"{kakao_hours:,.1f} 시간"),
            ("아웃룩 캘린더 공수", f"{outlook_hours:,.1f} 시간"),
            ("참여 팀원 수", f"{tot_workers} 명"),
            ("지원 고객사 수", f"{tot_clients} 개사"),
            ("야간 및 주말 공수", f"야간 {night_hours:,.1f}h / 주말 {weekend_hours:,.1f}h")
        ]

        curr_r = 5
        for metric_name, metric_val in kpis:
            c1 = ws1.cell(row=curr_r, column=1, value=metric_name)
            c2 = ws1.cell(row=curr_r, column=2, value=metric_val)
            c1.font = font_td_bold
            c2.font = font_td
            c1.border = cell_border
            c2.border = cell_border
            c1.fill = fill_zebra if curr_r % 2 == 1 else fill_white
            c2.fill = fill_zebra if curr_r % 2 == 1 else fill_white
            c1.alignment = align_left
            c2.alignment = align_right
            curr_r += 1

        # 팀원별 요약 테이블 (Row 13부터)
        curr_r += 2
        ws1.cell(row=curr_r, column=1, value=f"👥 {team_name} 팀원별 전월 업무 투입 내역").font = font_sec_header
        curr_r += 1

        member_headers = [
            "순번", "성명", "직급", "카카오톡(건)", "카톡 공수(h)", 
            "아웃룩(건)", "아웃룩 공수(h)", "총 합계(건)", "총 투입공수(h)", 
            "야간(h)", "주말(h)", "공수 비중(%)"
        ]
        for col_idx, h in enumerate(member_headers, 1):
            cell = ws1.cell(row=curr_r, column=col_idx, value=h)
            cell.font = font_th
            cell.fill = fill_th_sub
            cell.alignment = align_center
            cell.border = cell_border

        curr_r += 1
        worker_group = data.groupby("worker_name") if not data.empty and "worker_name" in data.columns else []

        w_summary_list = []
        for w_name, w_df in worker_group:
            w_title = w_df["worker_title"].dropna().iloc[0] if "worker_title" in w_df.columns and not w_df["worker_title"].dropna().empty else ""
            k_sub = w_df[~w_df["is_outlook"]] if "is_outlook" in w_df.columns else w_df
            o_sub = w_df[w_df["is_outlook"]] if "is_outlook" in w_df.columns else pd.DataFrame()

            k_cnt = len(k_sub)
            k_h = round(k_sub["actual_hours"].sum(), 1) if "actual_hours" in k_sub.columns else 0.0
            o_cnt = len(o_sub)
            o_h = round(o_sub["actual_hours"].sum(), 1) if not o_sub.empty and "actual_hours" in o_sub.columns else 0.0
            tot_h = round(w_df["actual_hours"].sum(), 1) if "actual_hours" in w_df.columns else 0.0
            ngt_h = round(w_df[w_df.get("is_night_work") == True]["actual_hours"].sum(), 1) if "actual_hours" in w_df.columns and "is_night_work" in w_df.columns else 0.0
            wkd_h = round(w_df[w_df.get("is_weekend_work") == True]["actual_hours"].sum(), 1) if "actual_hours" in w_df.columns and "is_weekend_work" in w_df.columns else 0.0

            w_summary_list.append({
                "name": w_name, "title": w_title, "k_cnt": k_cnt, "k_h": k_h,
                "o_cnt": o_cnt, "o_h": o_h, "tot_cnt": len(w_df), "tot_h": tot_h,
                "ngt_h": ngt_h, "wkd_h": wkd_h
            })

        # 총 투입 공수 내림차순 정렬
        w_summary_list.sort(key=lambda x: x["tot_h"], reverse=True)

        for idx, item in enumerate(w_summary_list, 1):
            ratio = round((item["tot_h"] / tot_actual_hours * 100), 1) if tot_actual_hours > 0 else 0.0
            row_vals = [
                idx, item["name"], item["title"], item["k_cnt"], item["k_h"],
                item["o_cnt"], item["o_h"], item["tot_cnt"], item["tot_h"],
                item["ngt_h"], item["wkd_h"], f"{ratio:.1f}%"
            ]
            fill_row = fill_zebra if idx % 2 == 1 else fill_white
            for col_idx, val in enumerate(row_vals, 1):
                cell = ws1.cell(row=curr_r, column=col_idx, value=val)
                cell.font = font_td_bold if col_idx in [2, 9] else font_td
                cell.fill = fill_row
                cell.border = cell_border
                if col_idx in [1, 2, 3]:
                    cell.alignment = align_center
                elif col_idx in [4, 6, 8]:
                    cell.alignment = align_right
                    cell.number_format = '#,##0"건"'
                elif col_idx in [5, 7, 9, 10, 11]:
                    cell.alignment = align_right
                    cell.number_format = '0.0"h"'
                else:
                    cell.alignment = align_right
            curr_r += 1

        # 팀원 요약 합계 행
        tot_row_vals = [
            "합계", f"{tot_workers}명", "-", len(kakao_df), kakao_hours,
            len(outlook_df), outlook_hours, tot_records, tot_actual_hours,
            night_hours, weekend_hours, "100.0%"
        ]
        for col_idx, val in enumerate(tot_row_vals, 1):
            cell = ws1.cell(row=curr_r, column=col_idx, value=val)
            cell.font = font_total
            cell.fill = fill_tot
            cell.border = total_top_border
            if col_idx in [1, 2, 3]:
                cell.alignment = align_center
            elif col_idx in [4, 6, 8]:
                cell.alignment = align_right
                cell.number_format = '#,##0"건"'
            elif col_idx in [5, 7, 9, 10, 11]:
                cell.alignment = align_right
                cell.number_format = '0.0"h"'
            else:
                cell.alignment = align_right

        # ---------------------------------------------------------
        # Sheet 2: 카카오톡 업무 원장 (Kakao Worklog)
        # ---------------------------------------------------------
        ws2 = wb.create_sheet(title="카카오톡 업무 원장")
        ws2.views.sheetView[0].showGridLines = True

        ws2["A1"] = f"💬 {team_name} {month_str} 카카오톡 업무 지원 상세 원장"
        ws2["A1"].font = font_main_title
        ws2["A2"] = f"총 {len(kakao_df):,}건 | 총 공수: {kakao_hours:,.1f}시간"
        ws2["A2"].font = font_sub_title

        k_headers = [
            "순번", "시작보고시각", "완료보고시각", "상태", "작업구분", 
            "담당자", "직급", "고객사", "작업내용", "소요시간(h)", 
            "야간여부", "주말여부", "카카오톡 원본 메시지"
        ]
        for col_idx, h in enumerate(k_headers, 1):
            cell = ws2.cell(row=4, column=col_idx, value=h)
            cell.font = font_th
            cell.fill = fill_th_main
            cell.alignment = align_center
            cell.border = cell_border

        k_curr_r = 5
        for idx, (_, r) in enumerate(kakao_df.iterrows(), 1):
            st_str = r["start_time"].strftime("%Y-%m-%d %H:%M") if pd.notna(r.get("start_time")) else ""
            et_str = r["end_time"].strftime("%Y-%m-%d %H:%M") if pd.notna(r.get("end_time")) else ""
            status_kor = "완료" if str(r.get("status", "")).upper() == "COMPLETED" else "진행"
            h_val = float(r.get("actual_hours", 0.0) or 0.0)
            raw_msg = str(r.get("raw_start_message") or r.get("raw_end_message") or "")

            row_data = [
                idx, st_str, et_str, status_kor, str(r.get("log_type", "")),
                str(r.get("worker_name", "")), str(r.get("worker_title", "")), str(r.get("client_name", "")),
                str(r.get("task_description", "")), h_val,
                "야간" if r.get("is_night_work") else "-",
                "주말" if r.get("is_weekend_work") else "-",
                raw_msg[:150]
            ]
            fill_r = fill_zebra if idx % 2 == 1 else fill_white
            for col_idx, val in enumerate(row_data, 1):
                cell = ws2.cell(row=k_curr_r, column=col_idx, value=val)
                cell.font = font_td
                cell.fill = fill_r
                cell.border = cell_border
                if col_idx in [1, 2, 3, 4, 5, 6, 7, 11, 12]:
                    cell.alignment = align_center
                elif col_idx in [8, 9, 13]:
                    cell.alignment = align_left
                elif col_idx == 10:
                    cell.alignment = align_right
                    cell.number_format = '0.0"h"'
            k_curr_r += 1

        # ---------------------------------------------------------
        # Sheet 3: 아웃룩 캘린더 일정 원장 (Outlook Events)
        # ---------------------------------------------------------
        ws3 = wb.create_sheet(title="아웃룩 캘린더 원장")
        ws3.views.sheetView[0].showGridLines = True

        ws3["A1"] = f"📅 {team_name} {month_str} 아웃룩 캘린더 일정 상세 원장"
        ws3["A1"].font = font_main_title
        ws3["A2"] = f"총 {len(outlook_df):,}건 | 총 공수: {outlook_hours:,.1f}시간"
        ws3["A2"].font = font_sub_title

        o_headers = [
            "순번", "시작일시", "종료일시", "상태", "일정 구분", 
            "담당자", "직급", "일정 제목 (내용)", "인정 공수(h)"
        ]
        for col_idx, h in enumerate(o_headers, 1):
            cell = ws3.cell(row=4, column=col_idx, value=h)
            cell.font = font_th
            cell.fill = fill_th_sub
            cell.alignment = align_center
            cell.border = cell_border

        o_curr_r = 5
        if not outlook_df.empty:
            for idx, (_, r) in enumerate(outlook_df.iterrows(), 1):
                st_str = r["start_time"].strftime("%Y-%m-%d %H:%M") if pd.notna(r.get("start_time")) else ""
                et_str = r["end_time"].strftime("%Y-%m-%d %H:%M") if pd.notna(r.get("end_time")) else ""
                status_kor = "완료" if str(r.get("status", "")).upper() == "COMPLETED" else "예정"
                h_val = float(r.get("actual_hours", 0.0) or 0.0)

                row_data = [
                    idx, st_str, et_str, status_kor, str(r.get("log_type", "아웃룩")),
                    str(r.get("worker_name", "")), str(r.get("worker_title", "")),
                    str(r.get("task_description", "")), h_val
                ]
                fill_r = fill_zebra if idx % 2 == 1 else fill_white
                for col_idx, val in enumerate(row_data, 1):
                    cell = ws3.cell(row=o_curr_r, column=col_idx, value=val)
                    cell.font = font_td
                    cell.fill = fill_r
                    cell.border = cell_border
                    if col_idx in [1, 2, 3, 4, 5, 6, 7]:
                        cell.alignment = align_center
                    elif col_idx == 8:
                        cell.alignment = align_left
                    elif col_idx == 9:
                        cell.alignment = align_right
                        cell.number_format = '0.0"h"'
                o_curr_r += 1
        else:
            ws3.cell(row=5, column=1, value="해당 월에 등록된 아웃룩 일정이 없습니다.").font = font_td

        # ---------------------------------------------------------
        # Sheet 4: 전체 통합 원장 (Combined Ledger)
        # ---------------------------------------------------------
        ws4 = wb.create_sheet(title="전체 통합 원장")
        ws4.views.sheetView[0].showGridLines = True

        ws4["A1"] = f"📑 {team_name} {month_str} 카카오톡 및 아웃룩 전체 통합 원장"
        ws4["A1"].font = font_main_title
        ws4["A2"] = f"총 {tot_records:,}건 | 총 합계 공수: {tot_actual_hours:,.1f}시간"
        ws4["A2"].font = font_sub_title

        all_headers = [
            "순번", "채널/구분", "시작시각", "종료시각", "상태", 
            "담당자", "직급", "고객사 / 분류", "작업 및 일정 상세", 
            "소요시간(h)", "야간", "주말"
        ]
        for col_idx, h in enumerate(all_headers, 1):
            cell = ws4.cell(row=4, column=col_idx, value=h)
            cell.font = font_th
            cell.fill = fill_th_main
            cell.alignment = align_center
            cell.border = cell_border

        all_curr_r = 5
        for idx, (_, r) in enumerate(data.iterrows(), 1):
            channel_str = "📅 아웃룩" if r.get("is_outlook") else "💬 카카오톡"
            st_str = r["start_time"].strftime("%Y-%m-%d %H:%M") if pd.notna(r.get("start_time")) else ""
            et_str = r["end_time"].strftime("%Y-%m-%d %H:%M") if pd.notna(r.get("end_time")) else ""
            status_kor = "완료" if str(r.get("status", "")).upper() == "COMPLETED" else "진행"
            h_val = float(r.get("actual_hours", 0.0) or 0.0)
            client_or_type = str(r.get("client_name") or r.get("log_type") or "-")

            row_data = [
                idx, channel_str, st_str, et_str, status_kor,
                str(r.get("worker_name", "")), str(r.get("worker_title", "")),
                client_or_type, str(r.get("task_description", "")), h_val,
                "야간" if r.get("is_night_work") else "-",
                "주말" if r.get("is_weekend_work") else "-"
            ]
            fill_r = fill_zebra if idx % 2 == 1 else fill_white
            for col_idx, val in enumerate(row_data, 1):
                cell = ws4.cell(row=all_curr_r, column=col_idx, value=val)
                cell.font = font_td
                cell.fill = fill_r
                cell.border = cell_border
                if col_idx in [1, 2, 3, 4, 5, 6, 7, 11, 12]:
                    cell.alignment = align_center
                elif col_idx in [8, 9]:
                    cell.alignment = align_left
                elif col_idx == 10:
                    cell.alignment = align_right
                    cell.number_format = '0.0"h"'
            all_curr_r += 1

        # 기본 빈 시트 제거
        if default_sheet in wb.worksheets:
            wb.remove(default_sheet)

        # 전체 시트 자동 열 너비 보정
        for ws in wb.worksheets:
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    if cell.row < 4:
                        continue
                    v_str = str(cell.value or "")
                    v_len = sum(2 if ord(ch) > 127 else 1 for ch in v_str)
                    if v_len > max_len:
                        max_len = v_len
                ws.column_dimensions[col_letter].width = max(min(max_len + 4, 45), 11)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

    # =========================================================
    # 4. 이메일 HTML 본문 생성 (Cisco ACI 스타일)
    # =========================================================
    @classmethod
    def generate_email_html(cls, team_name: str, month_str: str, df: pd.DataFrame) -> Tuple[str, str]:
        """
        이메일 제목과 Cisco ACI 표준 세련된 HTML 본문 생성
        """
        subject = f"[기술본부] {team_name} {month_str} 전월 업무 원장(카톡/아웃룩) 정기 보고"

        tot_records = len(df)
        kakao_df = df[~df["is_outlook"]] if "is_outlook" in df.columns else df
        outlook_df = df[df["is_outlook"]] if "is_outlook" in df.columns else pd.DataFrame()

        tot_actual_hours = round(df["actual_hours"].sum(), 1) if "actual_hours" in df.columns else 0.0
        kakao_hours = round(kakao_df["actual_hours"].sum(), 1) if "actual_hours" in kakao_df.columns else 0.0
        outlook_hours = round(outlook_df["actual_hours"].sum(), 1) if not outlook_df.empty and "actual_hours" in outlook_df.columns else 0.0
        tot_workers = df["worker_name"].nunique() if "worker_name" in df.columns else 0
        tot_clients = kakao_df["client_name"].nunique() if not kakao_df.empty and "client_name" in kakao_df.columns else 0

        # 팀원별 요약 생성
        worker_group = df.groupby("worker_name") if not df.empty and "worker_name" in df.columns else []
        w_summary_list = []
        for w_name, w_df in worker_group:
            w_title = w_df["worker_title"].dropna().iloc[0] if "worker_title" in w_df.columns and not w_df["worker_title"].dropna().empty else ""
            k_sub = w_df[~w_df["is_outlook"]] if "is_outlook" in w_df.columns else w_df
            o_sub = w_df[w_df["is_outlook"]] if "is_outlook" in w_df.columns else pd.DataFrame()
            tot_h = round(w_df["actual_hours"].sum(), 1) if "actual_hours" in w_df.columns else 0.0
            w_summary_list.append({
                "name": w_name, "title": w_title,
                "k_cnt": len(k_sub), "k_h": round(k_sub["actual_hours"].sum(), 1) if "actual_hours" in k_sub.columns else 0.0,
                "o_cnt": len(o_sub), "o_h": round(o_sub["actual_hours"].sum(), 1) if not o_sub.empty and "actual_hours" in o_sub.columns else 0.0,
                "tot_cnt": len(w_df), "tot_h": tot_h
            })
        w_summary_list.sort(key=lambda x: x["tot_h"], reverse=True)

        # 팀원 행 HTML
        table_rows_html = []
        for idx, item in enumerate(w_summary_list, 1):
            bg = "#ffffff" if idx % 2 == 1 else "#f8fafc"
            table_rows_html.append(f"""
            <tr style="background: {bg}; border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                <td style="padding: 10px 8px; text-align: center; color: #64748b;">{idx}</td>
                <td style="padding: 10px 8px; text-align: center; font-weight: 700; color: #0f172a;">{item['name']}</td>
                <td style="padding: 10px 8px; text-align: center; color: #475569;">{item['title']}</td>
                <td style="padding: 10px 8px; text-align: right; color: #0284c7;">{item['k_cnt']}건 ({item['k_h']:.1f}h)</td>
                <td style="padding: 10px 8px; text-align: right; color: #7c3aed;">{item['o_cnt']}건 ({item['o_h']:.1f}h)</td>
                <td style="padding: 10px 8px; text-align: right; font-weight: 800; color: #002d42;">{item['tot_h']:.1f}h</td>
            </tr>
            """)
        table_rows_str = "".join(table_rows_html)

        html_content = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
        </head>
        <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Malgun Gothic', '맑은 고딕', helvetica, sans-serif; -webkit-font-smoothing: antialiased;">
            <div style="max-width: 680px; margin: 25px auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0, 45, 66, 0.08); border: 1px solid #e2e8f0;">
                
                <!-- 상단 헤더 -->
                <div style="background: linear-gradient(135deg, #002D42 0%, #005073 100%); padding: 28px 32px; color: #ffffff;">
                    <div style="font-size: 11.5px; font-weight: 800; letter-spacing: 1px; color: #38bdf8; margin-bottom: 6px; text-transform: uppercase;">
                        FIELD SUPPORT PORTAL | MONTHLY WORKLOG REPORT
                    </div>
                    <h1 style="margin: 0; font-size: 21px; font-weight: 800; line-height: 1.35; color: #ffffff;">
                        {team_name} {month_str} 전월 업무 원장 정기 보고
                    </h1>
                    <div style="font-size: 12.5px; color: #94a3b8; margin-top: 8px;">
                        📅 발송 기준: 매월 1일 전월 실적 자동 마감 | 대상 기간: <b>{month_str}</b>
                    </div>
                </div>

                <!-- 본문 안내문 -->
                <div style="padding: 24px 32px 16px 32px;">
                    <div style="background: #f0f9ff; border-left: 4px solid #0284c7; padding: 14px 18px; border-radius: 6px; font-size: 13.5px; color: #0369a1; line-height: 1.6; margin-bottom: 22px;">
                        📌 <b>{team_name}</b> 소속 인원 전체에 대한 <b>{month_str} 전월 카카오톡 업무 지원 기록 및 아웃룩 캘린더 일정 원장</b>을 집계하여 송부드립니다.<br>
                        상세 다중 시트 원장은 첨부된 엑셀 파일(<b>{team_name}_{month_str.replace('-', '')}_업무원장_통합리포트.xlsx</b>)을 참조하여 주시기 바랍니다.
                    </div>

                    <!-- 핵심 지표 요약 카드 그리드 -->
                    <div style="display: table; width: 100%; margin-bottom: 22px;">
                        <div style="display: table-row;">
                            <div style="display: table-cell; width: 32%; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; text-align: center;">
                                <div style="font-size: 11px; color: #64748b; font-weight: 700;">총 투입 공수</div>
                                <div style="font-size: 22px; font-weight: 900; color: #002d42; margin-top: 4px;">{tot_actual_hours:,.1f}<span style="font-size: 13px; font-weight: 600;">h</span></div>
                            </div>
                            <div style="display: table-cell; width: 2%;"></div>
                            <div style="display: table-cell; width: 32%; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; text-align: center;">
                                <div style="font-size: 11px; color: #64748b; font-weight: 700;">총 지원/일정</div>
                                <div style="font-size: 22px; font-weight: 900; color: #0284c7; margin-top: 4px;">{tot_records:,}<span style="font-size: 13px; font-weight: 600;">건</span></div>
                            </div>
                            <div style="display: table-cell; width: 2%;"></div>
                            <div style="display: table-cell; width: 32%; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; text-align: center;">
                                <div style="font-size: 11px; color: #64748b; font-weight: 700;">참여 팀원</div>
                                <div style="font-size: 22px; font-weight: 900; color: #16a34a; margin-top: 4px;">{tot_workers}<span style="font-size: 13px; font-weight: 600;">명</span></div>
                            </div>
                        </div>
                    </div>

                    <!-- 팀원별 실적 요약 테이블 -->
                    <div style="margin-top: 10px; margin-bottom: 24px;">
                        <div style="font-size: 14px; font-weight: 800; color: #002d42; margin-bottom: 10px; display: flex; align-items: center; gap: 6px;">
                            <span>👥</span> <span>{team_name} 팀원별 전월 업무 투입 현황</span>
                        </div>
                        <table style="width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1; border-radius: 6px; overflow: hidden;">
                            <thead>
                                <tr style="background: #002D42; color: #ffffff; font-size: 12.5px;">
                                    <th style="padding: 10px 8px; text-align: center;">순번</th>
                                    <th style="padding: 10px 8px; text-align: center;">성명</th>
                                    <th style="padding: 10px 8px; text-align: center;">직급</th>
                                    <th style="padding: 10px 8px; text-align: right;">💬 카카오톡</th>
                                    <th style="padding: 10px 8px; text-align: right;">📅 아웃룩</th>
                                    <th style="padding: 10px 8px; text-align: right;">총 공수</th>
                                </tr>
                            </thead>
                            <tbody>
                                {table_rows_str}
                                <tr style="background: #e2e8f0; font-weight: 800; font-size: 13px; border-top: 2px solid #002d42;">
                                    <td colspan="3" style="padding: 10px 8px; text-align: center; color: #002d42;">합계 ({tot_workers}명)</td>
                                    <td style="padding: 10px 8px; text-align: right; color: #0284c7;">{len(kakao_df):,}건 ({kakao_hours:,.1f}h)</td>
                                    <td style="padding: 10px 8px; text-align: right; color: #7c3aed;">{len(outlook_df):,}건 ({outlook_hours:,.1f}h)</td>
                                    <td style="padding: 10px 8px; text-align: right; color: #002d42;">{tot_actual_hours:,.1f}h</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    <!-- 첨부파일 안내 카드 -->
                    <div style="background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 14px 18px; margin-bottom: 20px;">
                        <div style="font-size: 13px; font-weight: 700; color: #0f172a; margin-bottom: 4px;">
                            📎 첨부 파일: {team_name}_{month_str.replace('-', '')}_업무원장_통합리포트.xlsx
                        </div>
                        <div style="font-size: 12px; color: #64748b; line-height: 1.5;">
                            • 시트 1: 요약 현황 (핵심 KPI 및 팀원별 실적 비교표)<br>
                            • 시트 2: 카카오톡 업무 지원 상세 원장 (고객사, 작업내용, 소요시간 등)<br>
                            • 시트 3: 아웃룩 캘린더 일정 상세 원장 (회의, 외근, 연차 등)<br>
                            • 시트 4: 카톡 + 아웃룩 전체 통합 원장
                        </div>
                    </div>

                </div>

                <!-- 푸터 -->
                <div style="background: #f8fafc; border-top: 1px solid #e2e8f0; padding: 20px 32px; font-size: 11.5px; color: #94a3b8; line-height: 1.6;">
                    본 메일은 기술본부 업무관제 시스템의 월간 정기 배치 스케줄러(매월 1일 08:00)에 의해 자동으로 생성되어 발송되었습니다.<br>
                    궁금하신 사항은 기술본부 시스템 담당자에게 문의해 주시기 바랍니다.
                </div>

            </div>
        </body>
        </html>
        """
        return subject, html_content

    # =========================================================
    # 5. 메일 실제 발송 오케스트레이터
    # =========================================================
    @classmethod
    def send_monthly_team_report(
        cls,
        team_name: str = "기술 1팀",
        recipient_email: Optional[str] = None,
        month_str: Optional[str] = None,
        dispatch_type: str = "MANUAL_IMMEDIATE"
    ) -> Tuple[bool, str]:
        """
        팀 대표 메일로 전월 카톡/아웃룩 엑셀 원장 발송
        """
        cfg = cls.get_team_config(team_name)
        target_email = recipient_email.strip() if recipient_email else cfg.get("team_email", "GE101@sangsanginworld.co.kr")
        if not target_email:
            return False, "수신 팀 메일 주소가 설정되지 않았습니다."

        if not month_str:
            month_str = cls.get_previous_month()

        # 데이터 추출
        team_df = cls.get_team_monthly_data(team_name, month_str)
        if team_df.empty:
            return False, f"[{team_name}] {month_str} 기간에 등록된 업무 및 일정 데이터가 없습니다."

        # 엑셀 원장 파일 생성
        excel_bytes = cls.generate_monthly_worklog_excel(team_df, team_name, month_str)
        subject, html_content = cls.generate_email_html(team_name, month_str, team_df)

        sender = "newprim82@gmail.com"
        password = "dlugbvfuhgdozkgr"
        recipients = [em.strip() for em in target_email.split(",") if em.strip()]

        try:
            msg = MIMEMultipart("mixed")
            msg["Subject"] = Header(subject, "utf-8")
            from_name_b64 = base64.b64encode("기술본부 업무관제 시스템".encode("utf-8")).decode("ascii")
            msg["From"] = f"=?UTF-8?B?{from_name_b64}?= <{sender}>"
            msg["To"] = ", ".join(recipients)
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain="gmail.com")
            msg["Reply-To"] = sender
            msg["X-Mailer"] = "Monthly Team Worklog Reporter v1.0"

            # 본문 첨부
            msg_body = MIMEMultipart("alternative")
            msg_body.attach(MIMEText(html_content, "html", "utf-8"))
            msg.attach(msg_body)

            # 엑셀 파일 첨부
            clean_team_fn = team_name.replace(" ", "")
            clean_month_fn = month_str.replace("-", "")
            excel_filename = f"{clean_team_fn}_{clean_month_fn}_전월_업무원장_통합리포트.xlsx"
            excel_attachment = MIMEApplication(excel_bytes, _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            excel_attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=excel_filename
            )
            msg.attach(excel_attachment)

            # SMTP 전송 (SSL -> TLS Fallback)
            try:
                server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20)
                server.login(sender, password)
                server.sendmail(sender, recipients, msg.as_string())
                server.quit()
            except Exception:
                server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
                server.starttls()
                server.login(sender, password)
                server.sendmail(sender, recipients, msg.as_string())
                server.quit()

            # DB 발송 이력 기록
            EmailDispatchService.record_dispatch(
                dispatch_type=dispatch_type,
                recipient_emails=", ".join(recipients),
                sender_email=sender,
                selected_team=team_name,
                period_label=f"{team_name} {month_str} 전월 원장",
                subject=subject,
                status="SUCCESS"
            )

            return True, f"✅ [{team_name}] {month_str} 전월 업무 원장이 {', '.join(recipients)} 주소로 성공적으로 발송되었습니다!"

        except smtplib.SMTPAuthenticationError as e:
            err_msg = f"❌ Gmail 인증 실패: 구글 앱 비밀번호를 확인해주세요 ({e})"
            EmailDispatchService.record_dispatch(
                dispatch_type=dispatch_type,
                recipient_emails=", ".join(recipients),
                sender_email=sender,
                selected_team=team_name,
                period_label=f"{team_name} {month_str} 전월 원장",
                subject=subject,
                status="FAILED",
                error_message=err_msg
            )
            return False, err_msg
        except Exception as e:
            err_msg = f"❌ 메일 발송 실패: {str(e)}"
            EmailDispatchService.record_dispatch(
                dispatch_type=dispatch_type,
                recipient_emails=", ".join(recipients),
                sender_email=sender,
                selected_team=team_name,
                period_label=f"{team_name} {month_str} 전월 원장",
                subject=subject,
                status="FAILED",
                error_message=err_msg
            )
            return False, err_msg
