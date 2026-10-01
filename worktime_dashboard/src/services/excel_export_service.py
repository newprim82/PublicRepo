# -*- coding: utf-8 -*-
import io
import re
from datetime import datetime
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


class ExcelExportService:
    """
    정기 업무 투입 현황 리포트 Excel 내보내기 서비스
    다중 시트 구성:
      1. 요약 현황
      2. 팀원별 투입 현황
      3. 고객사별 투입 현황
      4. 상세 작업 원장
    """

    @classmethod
    def generate_report(cls, df: pd.DataFrame, title_suffix: str = "") -> bytes:
        if df.empty:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "데이터 없음"
            ws["A1"] = "조회된 데이터가 없습니다."
            output = io.BytesIO()
            wb.save(output)
            output.seek(0)
            return output.getvalue()

        # 데이터 안전 복사 및 전처리
        data = df.copy()
        for dt_col in ["start_time", "end_time"]:
            if dt_col in data.columns:
                data[dt_col] = pd.to_datetime(data[dt_col], errors="coerce")

        wb = openpyxl.Workbook()
        # 기본 시트 제거를 위해 참조 보관
        default_sheet = wb.active

        # 색상 및 스타일 정의
        navy_dark = "002D42"
        navy_light = "F0F9FF"
        navy_sub = "0284C7"
        gray_bg = "F8FAFC"
        border_light = Side(border_style="thin", color="E2E8F0")
        box_border = Border(left=border_light, right=border_light, top=border_light, bottom=border_light)
        
        font_title = Font(name="맑은 고딕", size=15, bold=True, color="002D42")
        font_subtitle = Font(name="맑은 고딕", size=10, color="64748B")
        font_th = Font(name="맑은 고딕", size=10.5, bold=True, color="FFFFFF")
        font_td = Font(name="맑은 고딕", size=10)
        font_td_bold = Font(name="맑은 고딕", size=10, bold=True)
        
        fill_th = PatternFill(start_color=navy_dark, end_color=navy_dark, fill_type="solid")
        fill_sub_th = PatternFill(start_color=navy_sub, end_color=navy_sub, fill_type="solid")
        fill_zebra = PatternFill(start_color=gray_bg, end_color=gray_bg, fill_type="solid")
        fill_white = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

        # =========================================================
        # Sheet 1: 요약 현황
        # =========================================================
        ws1 = wb.create_sheet(title="요약 현황")
        ws1.views.sheetView[0].showGridLines = True
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        period_text = title_suffix if title_suffix else "전체 기간"
        
        ws1["A1"] = f"📊 정기 업무 투입 현황 리포트 ({period_text})"
        ws1["A1"].font = font_title
        ws1["A2"] = f"출력 일시: {now_str} | 대상 레코드: {len(data):,}건"
        ws1["A2"].font = font_subtitle

        # 핵심 지표 산출
        active_df = data[data["status"].isin(["COMPLETED", "PENDING"])] if "status" in data.columns else data
        tot_hours = round(active_df["actual_hours"].sum(), 1) if "actual_hours" in active_df.columns else 0.0
        tot_tasks = len(active_df)
        comp_tasks = len(active_df[active_df["status"] == "COMPLETED"]) if "status" in active_df.columns else 0
        pend_tasks = len(active_df[active_df["status"] == "PENDING"]) if "status" in active_df.columns else 0
        tot_workers = active_df["worker_name"].nunique() if "worker_name" in active_df.columns else 0
        tot_clients = active_df["client_name"].nunique() if "client_name" in active_df.columns else 0
        night_hours = round(active_df[active_df["is_night_work"] == True]["actual_hours"].sum(), 1) if "is_night_work" in active_df.columns else 0.0
        weekend_hours = round(active_df[active_df["is_weekend_work"] == True]["actual_hours"].sum(), 1) if "is_weekend_work" in active_df.columns else 0.0

        summary_metrics = [
            ("총 투입 공수", f"{tot_hours:,.1f} 시간"),
            ("총 지원 건수", f"{tot_tasks:,} 건 (완료: {comp_tasks:,} / 진행: {pend_tasks:,})"),
            ("투입 인원", f"{tot_workers} 명"),
            ("지원 고객사", f"{tot_clients} 개사"),
            ("야간 근무 공수", f"{night_hours:,.1f} 시간"),
            ("주말 근무 공수", f"{weekend_hours:,.1f} 시간"),
        ]

        ws1["A4"] = "구분"
        ws1["B4"] = "실적 지표"
        for col_letter in ["A", "B"]:
            cell = ws1[f"{col_letter}4"]
            cell.font = font_th
            cell.fill = fill_th
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = box_border

        for r_idx, (m_label, m_val) in enumerate(summary_metrics, start=5):
            c1 = ws1[f"A{r_idx}"]
            c2 = ws1[f"B{r_idx}"]
            c1.value = m_label
            c2.value = m_val
            c1.font = font_td_bold
            c2.font = font_td
            c1.border = box_border
            c2.border = box_border
            c1.fill = fill_zebra if r_idx % 2 == 1 else fill_white
            c2.fill = fill_zebra if r_idx % 2 == 1 else fill_white
            c1.alignment = Alignment(horizontal="left", vertical="center")
            c2.alignment = Alignment(horizontal="right", vertical="center")

        # 팀별 집계 표 (Sheet 1 하단)
        if "worker_team" in active_df.columns:
            start_r = 13
            ws1[f"A{start_r}"] = "소속팀별 공수 점유율"
            ws1[f"A{start_r}"].font = font_title
            start_r += 1

            t_cols = ["소속팀", "투입 인원(명)", "작업 건수", "총 투입공수(h)", "점유율(%)"]
            for c_i, c_name in enumerate(t_cols, start=1):
                c_cell = ws1.cell(row=start_r, column=c_i, value=c_name)
                c_cell.font = font_th
                c_cell.fill = fill_sub_th
                c_cell.alignment = Alignment(horizontal="center", vertical="center")
                c_cell.border = box_border

            team_grp = active_df.groupby("worker_team").agg(
                workers=("worker_name", "nunique"),
                tasks=("worker_name", "count"),
                hours=("actual_hours", "sum")
            ).reset_index().sort_values(by="hours", ascending=False)

            for t_idx, row in team_grp.iterrows():
                start_r += 1
                share = (row["hours"] / tot_hours * 100.0) if tot_hours > 0 else 0.0
                vals = [row["worker_team"], row["workers"], row["tasks"], round(row["hours"], 1), f"{share:.1f}%"]
                for c_i, v in enumerate(vals, start=1):
                    cell = ws1.cell(row=start_r, column=c_i, value=v)
                    cell.font = font_td
                    cell.border = box_border
                    cell.fill = fill_zebra if start_r % 2 == 1 else fill_white
                    cell.alignment = Alignment(horizontal="center" if c_i <= 3 else "right", vertical="center")

        # =========================================================
        # Sheet 2: 팀원별 투입 현황
        # =========================================================
        ws2 = wb.create_sheet(title="팀원별 투입 현황")
        ws2.views.sheetView[0].showGridLines = True
        
        ws2["A1"] = f"👥 팀원별 업무 투입 실적 ({period_text})"
        ws2["A1"].font = font_title

        w_headers = ["담당자", "소속팀", "직급", "총 작업건수", "총 투입공수(h)", "일반공수(h)", "야간공수(h)", "주말공수(h)", "완료건수", "진행건수"]
        for c_i, h_name in enumerate(w_headers, start=1):
            cell = ws2.cell(row=3, column=c_i, value=h_name)
            cell.font = font_th
            cell.fill = fill_th
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = box_border

        if "worker_name" in active_df.columns:
            w_rows = []
            for w_name, w_df in active_df.groupby("worker_name"):
                w_team = w_df["worker_team"].iloc[0] if "worker_team" in w_df.columns and not w_df["worker_team"].isna().all() else ""
                w_title = w_df["worker_title"].iloc[0] if "worker_title" in w_df.columns and not w_df["worker_title"].isna().all() else ""
                tot_h = round(w_df["actual_hours"].sum(), 1) if "actual_hours" in w_df.columns else 0.0
                night_h = round(w_df[w_df["is_night_work"] == True]["actual_hours"].sum(), 1) if "is_night_work" in w_df.columns else 0.0
                week_h = round(w_df[w_df["is_weekend_work"] == True]["actual_hours"].sum(), 1) if "is_weekend_work" in w_df.columns else 0.0
                day_h = max(0.0, round(tot_h - (night_h + week_h), 1))
                t_cnt = len(w_df)
                c_cnt = len(w_df[w_df["status"] == "COMPLETED"]) if "status" in w_df.columns else 0
                p_cnt = len(w_df[w_df["status"] == "PENDING"]) if "status" in w_df.columns else 0
                w_rows.append((w_name, w_team, w_title, t_cnt, tot_h, day_h, night_h, week_h, c_cnt, p_cnt))

            w_rows.sort(key=lambda x: x[4], reverse=True)

            for r_i, w_data in enumerate(w_rows, start=4):
                for c_i, v in enumerate(w_data, start=1):
                    cell = ws2.cell(row=r_i, column=c_i, value=v)
                    cell.font = font_td
                    cell.border = box_border
                    cell.fill = fill_zebra if r_i % 2 == 1 else fill_white
                    cell.alignment = Alignment(horizontal="center" if c_i <= 3 else "right", vertical="center")

        # =========================================================
        # Sheet 3: 고객사별 투입 현황
        # =========================================================
        ws3 = wb.create_sheet(title="고객사별 투입 현황")
        ws3.views.sheetView[0].showGridLines = True

        ws3["A1"] = f"🏢 고객사별 지원 실적 ({period_text})"
        ws3["A1"].font = font_title

        c_headers = ["고객사명", "총 작업건수", "총 투입공수(h)", "점유율(%)", "투입 인원수", "주요 담당자"]
        for c_i, h_name in enumerate(c_headers, start=1):
            cell = ws3.cell(row=3, column=c_i, value=h_name)
            cell.font = font_th
            cell.fill = fill_th
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = box_border

        if "client_name" in active_df.columns:
            c_rows = []
            for c_name, c_df in active_df.groupby("client_name"):
                tot_h = round(c_df["actual_hours"].sum(), 1) if "actual_hours" in c_df.columns else 0.0
                t_cnt = len(c_df)
                share = (tot_h / tot_hours * 100.0) if tot_hours > 0 else 0.0
                u_workers = [str(w) for w in c_df["worker_name"].dropna().unique() if str(w).strip()]
                w_count = len(u_workers)
                top_workers_str = ", ".join(u_workers[:4]) + (" 외" if len(u_workers) > 4 else "")
                c_rows.append((c_name, t_cnt, tot_h, share, w_count, top_workers_str))

            c_rows.sort(key=lambda x: x[2], reverse=True)

            for r_i, c_data in enumerate(c_rows, start=4):
                vals = [c_data[0], c_data[1], c_data[2], f"{c_data[3]:.1f}%", c_data[4], c_data[5]]
                for c_i, v in enumerate(vals, start=1):
                    cell = ws3.cell(row=r_i, column=c_i, value=v)
                    cell.font = font_td
                    cell.border = box_border
                    cell.fill = fill_zebra if r_i % 2 == 1 else fill_white
                    if c_i == 1:
                        cell.alignment = Alignment(horizontal="left", vertical="center")
                    elif c_i == 6:
                        cell.alignment = Alignment(horizontal="left", vertical="center")
                    else:
                        cell.alignment = Alignment(horizontal="right", vertical="center")

        # =========================================================
        # Sheet 4: 상세 작업 원장
        # =========================================================
        ws4 = wb.create_sheet(title="상세 작업 원장")
        ws4.views.sheetView[0].showGridLines = True

        ws4["A1"] = f"📋 상세 작업 원장 ({period_text})"
        ws4["A1"].font = font_title

        raw_headers = [
            "구분", "담당자", "소속팀", "직급", "고객사", "작업내용",
            "시작일시", "종료일시", "예정(h)", "실제소요(h)", "상태",
            "야간작업", "주말작업"
        ]
        for c_i, h_name in enumerate(raw_headers, start=1):
            cell = ws4.cell(row=3, column=c_i, value=h_name)
            cell.font = font_th
            cell.fill = fill_th
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = box_border

        disp_raw = data.sort_values(by="start_time", ascending=False) if "start_time" in data.columns else data
        for r_i, (_, r) in enumerate(disp_raw.iterrows(), start=4):
            st_str = r["start_time"].strftime("%Y-%m-%d %H:%M") if pd.notna(r.get("start_time")) and hasattr(r["start_time"], "strftime") else str(r.get("start_time", ""))[:16]
            ed_str = r["end_time"].strftime("%Y-%m-%d %H:%M") if pd.notna(r.get("end_time")) and hasattr(r["end_time"], "strftime") else str(r.get("end_time", ""))[:16]

            row_vals = [
                str(r.get("log_type", "작업")),
                str(r.get("worker_name", "")),
                str(r.get("worker_team", "")),
                str(r.get("worker_title", "")),
                str(r.get("client_name", "")),
                str(r.get("task_description", "")),
                st_str,
                ed_str,
                round(float(r.get("estimated_hours") or 0), 1),
                round(float(r.get("actual_hours") or 0), 1),
                "완료" if str(r.get("status")) == "COMPLETED" else "진행중",
                "O" if bool(r.get("is_night_work")) else "",
                "O" if bool(r.get("is_weekend_work")) else "",
            ]

            for c_i, v in enumerate(row_vals, start=1):
                cell = ws4.cell(row=r_i, column=c_i, value=v)
                cell.font = font_td
                cell.border = box_border
                cell.fill = fill_zebra if r_i % 2 == 1 else fill_white
                if c_i in [1, 2, 3, 4, 11, 12, 13]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif c_i in [5, 6]:
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                elif c_i in [7, 8]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="right", vertical="center")

        # 기본 빈 시트 제거
        if default_sheet in wb.worksheets:
            wb.remove(default_sheet)

        # 모든 시트 자동 열 너비 계산 및 패딩 조정
        for ws in wb.worksheets:
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    if cell.row < 3:
                        continue
                    val_str = str(cell.value or "")
                    # 한글 등 멀티바이트 글자 길이 고려
                    val_len = sum(2 if ord(ch) > 127 else 1 for ch in val_str)
                    if val_len > max_len:
                        max_len = val_len
                ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

    @classmethod
    def generate_cost_estimation_report(
        cls,
        df_calc: pd.DataFrame,
        worker_df: pd.DataFrame,
        title_suffix: str = ""
    ) -> bytes:
        """
        💰 팀원별 예상 청구 금액 및 상세 투입 내역 다중 시트 Excel 리포트 생성
        - Sheet 1: 팀 전체 정산표 (전체 팀원 요약 + 합계 행)
        - Sheet 2 ~ N: 각 팀원별 상세 지원 내역 탭 (지원일시, 고객사, 업무내용, 공수, 할증배율, 금액 산정 내역)
        """
        if df_calc.empty or worker_df.empty:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "정산 데이터 없음"
            ws["A1"] = "조회 조건에 해당하는 정산 데이터가 없습니다."
            output = io.BytesIO()
            wb.save(output)
            output.seek(0)
            return output.getvalue()

        # 전처리
        data = df_calc.copy()
        for dt_col in ["start_time", "end_time"]:
            if dt_col in data.columns:
                data[dt_col] = pd.to_datetime(data[dt_col], errors="coerce")

        wb = openpyxl.Workbook()
        default_sheet = wb.active

        # 색상 및 스타일 정의
        navy_dark = "002D42"     # 다크 네이비 헤더
        navy_sub = "0284C7"      # 스카이 블루 (서브 헤더)
        gray_bg = "F8FAFC"       # 지브라 배경
        summary_bg = "E0F2FE"    # 요약/합계 행 배경
        border_light = Side(border_style="thin", color="CBD5E1")
        border_double = Side(border_style="double", color="002D42")
        border_top_thin = Side(border_style="thin", color="002D42")

        box_border = Border(left=border_light, right=border_light, top=border_light, bottom=border_light)
        total_border = Border(left=border_light, right=border_light, top=border_top_thin, bottom=border_double)

        font_title = Font(name="맑은 고딕", size=15, bold=True, color="002D42")
        font_subtitle = Font(name="맑은 고딕", size=10, color="64748B")
        font_th = Font(name="맑은 고딕", size=10.5, bold=True, color="FFFFFF")
        font_td = Font(name="맑은 고딕", size=10)
        font_td_bold = Font(name="맑은 고딕", size=10, bold=True, color="0F172A")
        font_total = Font(name="맑은 고딕", size=10.5, bold=True, color="002D42")

        fill_th = PatternFill(start_color=navy_dark, end_color=navy_dark, fill_type="solid")
        fill_sub_th = PatternFill(start_color=navy_sub, end_color=navy_sub, fill_type="solid")
        fill_zebra = PatternFill(start_color=gray_bg, end_color=gray_bg, fill_type="solid")
        fill_white = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        fill_total = PatternFill(start_color=summary_bg, end_color=summary_bg, fill_type="solid")

        align_center = Alignment(horizontal="center", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        period_text = title_suffix if title_suffix else "전체 기간"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # =========================================================
        # Sheet 1: 팀 전체 정산표
        # =========================================================
        ws_all = wb.create_sheet(title="팀 전체 정산표")
        ws_all.sheet_properties.tabColor = "002D42"
        ws_all.views.sheetView[0].showGridLines = True

        ws_all["A1"] = f"📊 팀원별 투입 공수 및 예상 청구 금액 정산표 ({period_text})"
        ws_all["A1"].font = font_title
        ws_all["A2"] = f"출력 일시: {now_str} | 대상 팀원: {len(worker_df):,}명 | 총 작업: {len(data):,}건"
        ws_all["A2"].font = font_subtitle

        headers_all = [
            "순번", "팀원명", "소속팀", "직급", "시간당 단가(원)",
            "총 인정공수(h)", "야간·주말(h)", "기본 금액(원)", "할증 가산액(원)", "최종 청구금액(원)",
            "작업 건수", "보정 건수"
        ]
        start_row = 4
        for col_idx, h in enumerate(headers_all, start=1):
            cell = ws_all.cell(row=start_row, column=col_idx, value=h)
            cell.font = font_th
            cell.fill = fill_th
            cell.alignment = align_center
            cell.border = box_border

        curr_row = start_row + 1
        for idx, (_, r) in enumerate(worker_df.iterrows(), start=1):
            row_data = [
                idx,
                str(r.get("worker_name", "")),
                str(r.get("worker_team", "")),
                str(r.get("worker_title", "")),
                int(r.get("hourly_rate", 0)),
                float(r.get("total_hours", 0.0)),
                float(r.get("overtime_hours", 0.0)),
                int(r.get("base_cost", 0)),
                int(r.get("overtime_premium", 0)),
                int(r.get("total_cost", 0)),
                int(r.get("task_count", 0)),
                int(r.get("adjusted_count", 0))
            ]

            fill_row = fill_zebra if idx % 2 == 1 else fill_white
            for col_idx, val in enumerate(row_data, start=1):
                cell = ws_all.cell(row=curr_row, column=col_idx, value=val)
                cell.font = font_td_bold if col_idx in [2, 10] else font_td
                cell.fill = fill_row
                cell.border = box_border

                if col_idx in [1, 3, 4]:
                    cell.alignment = align_center
                elif col_idx == 2:
                    cell.alignment = align_center
                elif col_idx in [5, 8, 9, 10]:
                    cell.alignment = align_right
                    cell.number_format = '#,##0"원"'
                elif col_idx in [6, 7]:
                    cell.alignment = align_right
                    cell.number_format = '0.0"h"'
                elif col_idx in [11, 12]:
                    cell.alignment = align_right
                    cell.number_format = '#,##0"건"'

            curr_row += 1

        # 합계 행 추가
        sum_total_hours = round(float(worker_df["total_hours"].sum()), 1) if "total_hours" in worker_df.columns else 0.0
        sum_ot_hours = round(float(worker_df["overtime_hours"].sum()), 1) if "overtime_hours" in worker_df.columns else 0.0
        sum_base = int(worker_df["base_cost"].sum()) if "base_cost" in worker_df.columns else 0
        sum_prem = int(worker_df["overtime_premium"].sum()) if "overtime_premium" in worker_df.columns else 0
        sum_cost = int(worker_df["total_cost"].sum()) if "total_cost" in worker_df.columns else 0
        sum_tasks = int(worker_df["task_count"].sum()) if "task_count" in worker_df.columns else 0
        sum_adjs = int(worker_df["adjusted_count"].sum()) if "adjusted_count" in worker_df.columns else 0

        tot_row_data = [
            "합계", f"{len(worker_df)}명", "-", "-", "-",
            sum_total_hours, sum_ot_hours, sum_base, sum_prem, sum_cost,
            sum_tasks, sum_adjs
        ]
        for col_idx, val in enumerate(tot_row_data, start=1):
            cell = ws_all.cell(row=curr_row, column=col_idx, value=val)
            cell.font = font_total
            cell.fill = fill_total
            cell.border = total_border

            if col_idx in [1, 2, 3, 4, 5]:
                cell.alignment = align_center
            elif col_idx in [6, 7]:
                cell.alignment = align_right
                cell.number_format = '0.0"h"'
            elif col_idx in [8, 9, 10]:
                cell.alignment = align_right
                cell.number_format = '#,##0"원"'
            elif col_idx in [11, 12]:
                cell.alignment = align_right
                cell.number_format = '#,##0"건"'

        curr_row += 2
        guide_cell = ws_all.cell(
            row=curr_row, column=1,
            value="💡 엑셀 하단의 팀원별 탭을 클릭하시면 개인별 상세 지원 내역(고객사, 시간대, 근로기준법 할증 배율 등)을 직접 확인하실 수 있습니다."
        )
        guide_cell.font = font_subtitle

        # =========================================================
        # Sheet 2 ~ N: 개인별 상세 탭
        # =========================================================
        existing_sheet_names = set(wb.sheetnames)

        for _, w_info in worker_df.iterrows():
            w_name = str(w_info.get("worker_name", "")).strip()
            if not w_name:
                continue

            w_team = str(w_info.get("worker_team", ""))
            w_title = str(w_info.get("worker_title", ""))
            w_rate = int(w_info.get("hourly_rate", 0))

            # 안전한 시트명 생성 (최대 31자, 특수문자 제거)
            safe_name = re.sub(r'[\\/*?:\[\]]', '', w_name).strip()
            tab_base = f"{safe_name}({w_title})" if w_title else safe_name
            tab_base = tab_base[:28]
            sheet_title = tab_base
            s_idx = 1
            while sheet_title in existing_sheet_names:
                suffix = f"_{s_idx}"
                sheet_title = f"{tab_base[:31-len(suffix)]}{suffix}"
                s_idx += 1
            existing_sheet_names.add(sheet_title)

            ws_p = wb.create_sheet(title=sheet_title)
            ws_p.sheet_properties.tabColor = "0284C7"
            ws_p.views.sheetView[0].showGridLines = True

            # 팀원별 데이터 필터링
            w_data = data[data["worker_name"] == w_name].copy()
            if "start_time" in w_data.columns:
                w_data = w_data.sort_values(by="start_time", ascending=True)

            w_tot_h = float(w_info.get("total_hours", 0.0))
            w_ot_h = float(w_info.get("overtime_hours", 0.0))
            w_base_c = int(w_info.get("base_cost", 0))
            w_prem_c = int(w_info.get("overtime_premium", 0))
            w_tot_c = int(w_info.get("total_cost", 0))
            w_task_cnt = int(w_info.get("task_count", len(w_data)))
            w_adj_cnt = int(w_info.get("adjusted_count", 0))

            # 상단 헤더 영역
            ws_p["A1"] = f"👤 {w_name} ({w_title}) 업무 지원 및 예상 청구 금액 상세 내역"
            ws_p["A1"].font = font_title
            ws_p["A2"] = f"소속: {w_team} | 직급: {w_title} | 적용 단가: ₩{w_rate:,}/h | 정산 기간: {period_text} | 출력: {now_str}"
            ws_p["A2"].font = font_subtitle

            ws_p["A3"] = f"📌 정산 요약: 총 인정공수 {w_tot_h:,.1f}h (야간·주말: {w_ot_h:,.1f}h) | 기본 금액 ₩{w_base_c:,.0f} | 할증 가산액 +₩{w_prem_c:,.0f} | 최종 청구금액 ₩{w_tot_c:,.0f} (총 {w_task_cnt:,}건)"
            ws_p["A3"].font = font_td_bold

            # 테이블 헤더
            p_headers = [
                "No.", "지원일자", "시작시각", "종료시각", "고객사명", "지원 업무 내용",
                "인정공수(h)", "근무구분", "할증배율", "시간당 단가(원)",
                "기본 금액(원)", "할증 가산액(원)", "최종 청구금액(원)", "공수보정", "비고"
            ]
            p_start_row = 5
            for col_idx, h in enumerate(p_headers, start=1):
                cell = ws_p.cell(row=p_start_row, column=col_idx, value=h)
                cell.font = font_th
                cell.fill = fill_th
                cell.alignment = align_center
                cell.border = box_border

            p_curr_row = p_start_row + 1
            for row_num, (_, r) in enumerate(w_data.iterrows(), start=1):
                st_dt = r.get("start_time")
                ed_dt = r.get("end_time")
                date_str = st_dt.strftime("%Y-%m-%d") if pd.notna(st_dt) and hasattr(st_dt, "strftime") else str(st_dt)[:10]
                st_time_str = st_dt.strftime("%H:%M") if pd.notna(st_dt) and hasattr(st_dt, "strftime") else str(st_dt)[11:16]
                ed_time_str = ed_dt.strftime("%H:%M") if pd.notna(ed_dt) and hasattr(ed_dt, "strftime") else str(ed_dt)[11:16]

                is_nt = bool(r.get("is_night_work", False))
                is_wk = bool(r.get("is_weekend_work", False))
                if is_nt and is_wk:
                    work_type = "야간+휴일"
                elif is_wk:
                    work_type = "주말·휴일"
                elif is_nt:
                    work_type = "야간근무"
                else:
                    work_type = "주간(일반)"

                mult = float(r.get("rate_multiplier", 1.0))
                mult_str = f"{mult:.1f}배"

                is_adj = bool(r.get("is_time_adjusted", False))
                adj_str = "수정보정" if is_adj else "정상"

                p_row_data = [
                    row_num,
                    date_str,
                    st_time_str,
                    ed_time_str,
                    str(r.get("client_name", "")),
                    str(r.get("task_description", "")),
                    float(r.get("billable_hours", 0.0)),
                    work_type,
                    mult_str,
                    int(r.get("hourly_rate", w_rate)),
                    int(r.get("base_cost", 0)),
                    int(r.get("overtime_premium", 0)),
                    int(r.get("estimated_cost", 0)),
                    adj_str,
                    str(r.get("note", ""))
                ]

                fill_p_row = fill_zebra if row_num % 2 == 1 else fill_white
                for col_idx, val in enumerate(p_row_data, start=1):
                    cell = ws_p.cell(row=p_curr_row, column=col_idx, value=val)
                    cell.font = font_td_bold if col_idx == 13 else font_td
                    cell.fill = fill_p_row
                    cell.border = box_border

                    if col_idx in [1, 2, 3, 4, 8, 9, 14]:
                        cell.alignment = align_center
                    elif col_idx in [5, 6, 15]:
                        cell.alignment = align_left
                    elif col_idx == 7:
                        cell.alignment = align_right
                        cell.number_format = '0.0"h"'
                    elif col_idx in [10, 11, 12, 13]:
                        cell.alignment = align_right
                        cell.number_format = '#,##0"원"'

                p_curr_row += 1

            # 팀원 개인 합계 행
            p_tot_data = [
                "합계", "-", "-", "-", "-", f"총 {len(w_data)}건 지원",
                w_tot_h, "-", "-", "-",
                w_base_c, w_prem_c, w_tot_c,
                f"{w_adj_cnt}건", "-"
            ]
            for col_idx, val in enumerate(p_tot_data, start=1):
                cell = ws_p.cell(row=p_curr_row, column=col_idx, value=val)
                cell.font = font_total
                cell.fill = fill_total
                cell.border = total_border

                if col_idx in [1, 2, 3, 4, 5, 8, 9, 10, 15]:
                    cell.alignment = align_center
                elif col_idx == 6:
                    cell.alignment = align_center
                elif col_idx == 7:
                    cell.alignment = align_right
                    cell.number_format = '0.0"h"'
                elif col_idx in [11, 12, 13]:
                    cell.alignment = align_right
                    cell.number_format = '#,##0"원"'
                elif col_idx == 14:
                    cell.alignment = align_center

        # 기본 빈 시트 제거
        if default_sheet in wb.worksheets:
            wb.remove(default_sheet)

        # 전체 시트 열 너비 자동 조정
        for ws in wb.worksheets:
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    if cell.row < 4:
                        continue
                    val_str = str(cell.value or "")
                    val_len = sum(2 if ord(ch) > 127 else 1 for ch in val_str)
                    if val_len > max_len:
                        max_len = val_len
                ws.column_dimensions[col_letter].width = max(min(max_len + 4, 50), 11)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

