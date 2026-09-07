import os
import io
import re
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from ...services.team_service import TeamService, UNASSIGNED_TEAM
from ...services.email_report_service import EmailReportService
from ...services.ai_briefing_service import FactExtractor, AIBriefingService
from ..common.dialogs import show_email_report_dialog
from ..common.ui_helpers import (
    strip_tz,
    get_job_title_badge,
    get_job_title_color,
    get_job_title_rank,
    get_team_theme,
    is_same_team,
    get_all_teams_safe,
    extract_week_sort_key,
    get_available_weeks_for_df,
    render_empty_week_notice
)

def render_work_summary_tab(df: pd.DataFrame, df_raw: pd.DataFrame, selected_team: str, team_mappings: dict, month_desc: str = ""):
    """[📊 업무 실적 Summary] 주간/월간 핵심 요약 & 메일 발송"""
    if df.empty:
        st.info("표시할 보고서 데이터가 없습니다.")
        return

    if not month_desc and "month_str" in df.columns:
        m_list = [str(m) for m in df["month_str"].dropna().unique() if str(m).strip()]
        month_desc = ", ".join(m_list) if m_list else ""

    # 상단 헤더 & 주간 리포트 이메일 발송 툴바 (AI 재분석 버튼과 동일한 0.8 컬럼 너비로 완벽 통일)
    h_col1, h_col2 = st.columns([4.2, 0.8])
    with h_col1:
        st.markdown(f"### 📊 {selected_team} - Summary")
        st.caption("주간/월간 전체 작업 실적 핵심 요약 브리핑 및 주간 정기 이메일 발송을 제공합니다.")
    with h_col2:
        st.markdown(
            """
            <style>
            div.st-key-btn_trigger_email_modal button {
                background-color: #004060 !important;
                background: linear-gradient(135deg, #002d42 0%, #005073 100%) !important;
                color: #FFFFFF !important;
                border: 1px solid rgba(255, 255, 255, 0.3) !important;
                border-radius: 6px !important;
                font-size: 13.5px !important;
                font-weight: 700 !important;
                height: 38px !important;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25) !important;
                transition: all 0.2s ease !important;
            }
            div.st-key-btn_trigger_email_modal button p {
                color: #FFFFFF !important;
                font-weight: 700 !important;
                font-size: 13.5px !important;
                letter-spacing: -0.2px !important;
            }
            div.st-key-btn_trigger_email_modal button:hover {
                background-color: #00608a !important;
                background: linear-gradient(135deg, #004060 0%, #0284c7 100%) !important;
                border-color: #38bdf8 !important;
                color: #FFFFFF !important;
                box-shadow: 0 4px 12px rgba(2, 132, 199, 0.45) !important;
                transform: translateY(-1px) !important;
            }
            div.st-key-btn_trigger_email_modal button:hover p {
                color: #FFFFFF !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        def render_email_report_button(team: str):
            if st.button("📧 메일 발송", use_container_width=True, key="btn_trigger_email_modal"):
                show_email_report_dialog(team)
        render_email_report_button(selected_team)

    st.write("")

    # =========================================================================
    # 0. 📅 보고서 조회 주기 선택 (월간 전체 종합 vs 각 주차별 상세 드릴다운)
    # =========================================================================
    df_scope = df.copy()
    available_weeks = get_available_weeks_for_df(df_scope, month_desc=month_desc)

    period_options = ["📅 월간 전체 종합"] + [f"📌 {w}" for w in available_weeks]
    
    st.markdown("""
    <style>
        div.st-key-exec_summary_period_selector [data-testid="stWidgetLabel"],
        div.st-key-exec_summary_period_selector [data-testid="stWidgetLabel"] *,
        div.st-key-exec_summary_period_selector label,
        div.st-key-exec_summary_period_selector label * {
            color: #002d42 !important;
            font-size: 14.5px !important;
            font-weight: 800 !important;
        }
        div.st-key-exec_summary_period_selector div[role="radiogroup"] {
            background: #ffffff !important;
            border: 1.5px solid #005f8a !important;
            border-radius: 8px !important;
            padding: 8px 14px !important;
            display: flex !important;
            flex-wrap: wrap !important;
            gap: 10px !important;
            box-shadow: 0 2px 6px rgba(0,45,66,0.06) !important;
            margin-bottom: 12px !important;
        }
        div.st-key-exec_summary_period_selector div[role="radiogroup"] label {
            background: #f1f5f9 !important;
            border: 1.2px solid #cbd5e1 !important;
            border-radius: 6px !important;
            padding: 5px 12px !important;
            margin: 0 !important;
            cursor: pointer !important;
            transition: all 0.15s ease-in-out !important;
        }
        div.st-key-exec_summary_period_selector div[role="radiogroup"] label:hover {
            background: #e2e8f0 !important;
            border-color: #0284c7 !important;
        }
        div.st-key-exec_summary_period_selector div[role="radiogroup"] label p,
        div.st-key-exec_summary_period_selector div[role="radiogroup"] label span {
            color: #002d42 !important;
            font-size: 13px !important;
            font-weight: 800 !important;
        }
        div.st-key-exec_summary_period_selector div[role="radiogroup"] label[data-checked="true"],
        div.st-key-exec_summary_period_selector div[role="radiogroup"] label:has(input:checked) {
            background: #005073 !important;
            border-color: #002d42 !important;
        }
        div.st-key-exec_summary_period_selector div[role="radiogroup"] label[data-checked="true"] p,
        div.st-key-exec_summary_period_selector div[role="radiogroup"] label:has(input:checked) p,
        div.st-key-exec_summary_period_selector div[role="radiogroup"] label[data-checked="true"] span,
        div.st-key-exec_summary_period_selector div[role="radiogroup"] label:has(input:checked) span {
            color: #ffffff !important;
            font-weight: 900 !important;
        }
    </style>
    <div style="font-size: 14.5px; font-weight: 800; color: #002d42 !important; margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
        <span>📅</span>
        <span style="color: #002d42 !important; font-weight: 800 !important;">보고서 조회 주기 선택 (월간 / 주간 드릴다운)</span>
    </div>
    """, unsafe_allow_html=True)

    if available_weeks:
        sel_period = st.radio(
            "보고서 조회 주기 선택 (월간 / 주간 드릴다운)",
            options=period_options,
            horizontal=True,
            key="exec_summary_period_selector",
            label_visibility="collapsed"
        )
    else:
        sel_period = "📅 월간 전체 종합"

    # 팀명 공백 무관 안전 비교 헬퍼
    def is_same_team(t1, t2):
        return str(t1).replace(" ", "").strip() == str(t2).replace(" ", "").strip()

    # 선택된 주기에 따른 활성 데이터셋(df_active) 및 전기 비교 데이터(prev_df) 분기
    if sel_period != "📅 월간 전체 종합":
        target_week = sel_period.replace("📌 ", "").strip()
        # 💡 월 경계(예: 8/31~9/6)에 걸친 주차도 7일 전체 데이터가 누락 없이 온전히 조회되도록 df_raw에서 주간 데이터 추출
        if "week_label" in df_raw.columns:
            df_active = df_raw[df_raw["week_label"] == target_week].copy()
        else:
            df_active = df_scope[df_scope["week_label"] == target_week].copy()

        if selected_team not in ["전체", "전체 팀"] and not df_active.empty:
            df_active["worker_team"] = df_active["worker_name"].map(team_mappings).fillna(df_active.get("worker_team", "")).fillna(UNASSIGNED_TEAM)
            df_active = df_active[df_active["worker_team"].apply(lambda t: is_same_team(t, selected_team))]

        current_period_label = f"{selected_team} - {target_week}"
        is_weekly_view = True

        # 직전 주차 찾기 (WoW 전주 대비 계산)
        cur_w_idx = available_weeks.index(target_week) if target_week in available_weeks else -1
        prev_df = pd.DataFrame()
        if cur_w_idx > 0:
            prev_week_label = available_weeks[cur_w_idx - 1]
            if "week_label" in df_raw.columns:
                prev_df = df_raw[df_raw["week_label"] == prev_week_label].copy()
            else:
                prev_df = df_scope[df_scope["week_label"] == prev_week_label].copy()
            if selected_team not in ["전체", "전체 팀"] and not prev_df.empty:
                prev_df["worker_team"] = prev_df["worker_name"].map(team_mappings).fillna(prev_df.get("worker_team", "")).fillna(UNASSIGNED_TEAM)
                prev_df = prev_df[prev_df["worker_team"].apply(lambda t: is_same_team(t, selected_team))]
        else:
            # 💡 월 첫 주차인 경우 -> 지난달 마지막 주차 (직전 7일 날짜 범위)를 df_raw 전체에서 추출!
            if "start_time" in df_active.columns and pd.notna(df_active["start_time"].min()):
                cur_min_dt = df_active["start_time"].min()
                cur_monday = cur_min_dt - pd.Timedelta(days=cur_min_dt.weekday())
                cur_monday_start = cur_monday.replace(hour=0, minute=0, second=0, microsecond=0)
                prev_monday_start = cur_monday_start - pd.Timedelta(days=7)
                prev_sunday_end = cur_monday_start - pd.Timedelta(seconds=1)

                if "start_time" in df_raw.columns:
                    raw_dt = pd.to_datetime(df_raw["start_time"], errors="coerce")
                    prev_df = df_raw[(raw_dt >= prev_monday_start) & (raw_dt <= prev_sunday_end)].copy()
                    if selected_team not in ["전체", "전체 팀"] and not prev_df.empty:
                        prev_df["worker_team"] = prev_df["worker_name"].map(team_mappings).fillna(prev_df.get("worker_team", "")).fillna(UNASSIGNED_TEAM)
                        prev_df = prev_df[prev_df["worker_team"].apply(lambda t: is_same_team(t, selected_team))]
    else:
        # ★ 사용자 지정 규칙: '월간 전체 종합'은 우측에 있는 모든 주차(available_weeks)를 기준으로 온전하게 집계! ★
        if available_weeks and "week_label" in df_raw.columns:
            df_active = df_raw[df_raw["week_label"].isin(available_weeks)].copy()
            if "msg_hash" in df_active.columns:
                df_active = df_active.drop_duplicates(subset=["msg_hash"])
        else:
            df_active = df_scope.copy()

        if selected_team not in ["전체", "전체 팀"] and not df_active.empty:
            df_active["worker_team"] = df_active["worker_name"].map(team_mappings).fillna(df_active.get("worker_team", "")).fillna(UNASSIGNED_TEAM)
            df_active = df_active[df_active["worker_team"].apply(lambda t: is_same_team(t, selected_team))]

        current_period_label = f"{selected_team} - {month_desc} 월간 전체" if month_desc else f"{selected_team} - 월간 전체"
        is_weekly_view = False

        # 직전 월 데이터 산출 (MoM 전월 대비 계산)
        prev_df = pd.DataFrame()
        if "start_time" in df_active.columns and pd.notna(df_active["start_time"].min()) and pd.notna(df_active["start_time"].max()):
            cur_min_dt = df_active["start_time"].min()
            cur_max_dt = df_active["start_time"].max()
            delta_days = max(1, (cur_max_dt.date() - cur_min_dt.date()).days + 1)
            prev_start = cur_min_dt - pd.Timedelta(days=delta_days)
            prev_end = cur_min_dt - pd.Timedelta(seconds=1)

            prev_df = df_raw[(df_raw["start_time"] >= prev_start) & (df_raw["start_time"] <= prev_end)].copy()
            if selected_team not in ["전체", "전체 팀"] and not prev_df.empty:
                prev_df["worker_team"] = prev_df["worker_name"].map(team_mappings).fillna(prev_df.get("worker_team", "")).fillna(UNASSIGNED_TEAM)
                prev_df = prev_df[prev_df["worker_team"].apply(lambda t: is_same_team(t, selected_team))]

    # ----------------------------------------------------
    # 데이터 유무 체크 및 빈 주차 안내
    # ----------------------------------------------------
    if is_weekly_view and df_active.empty:
        render_empty_week_notice(target_week, selected_team)

    # ----------------------------------------------------
    # 핵심 지표 산출
    # ----------------------------------------------------
    tot_hours = round(df_active["actual_hours"].sum(), 1)
    tot_cnt = len(df_active)
    tot_workers = df_active["worker_name"].nunique()
    tot_clients = df_active["client_name"].nunique()
    avg_hours_per_worker = round(tot_hours / tot_workers, 1) if tot_workers > 0 else 0.0

    # 예정시간 준수율 계산
    est_df = df_active[df_active["estimated_hours"] > 0]
    if not est_df.empty:
        on_time_cnt = (est_df["actual_hours"] <= est_df["estimated_hours"]).sum()
        overdue_cnt = (est_df["actual_hours"] > est_df["estimated_hours"]).sum()
        on_time_rate = round((on_time_cnt / len(est_df)) * 100, 1)
    else:
        overdue_cnt = 0
        on_time_rate = 100.0

    # 전기 비교 데이터 산출
    prev_tot_hours = None
    prev_tot_cnt = None
    prev_tot_clients = None
    prev_avg_hours = None

    if not prev_df.empty:
        prev_tot_hours = round(prev_df["actual_hours"].sum(), 1)
        prev_tot_cnt = len(prev_df)
        prev_tot_clients = prev_df["client_name"].nunique()
        prev_w_cnt = prev_df["worker_name"].nunique()
        prev_avg_hours = round(prev_tot_hours / prev_w_cnt, 1) if prev_w_cnt > 0 else 0.0

    def get_delta_badge(cur_val, prev_val, is_positive_good=True):
        if prev_val is None or prev_val == 0 or pd.isna(prev_val):
            return "<span style='color:#94a3b8; font-size:11.5px; font-weight:600;'>전기 비교불가</span>"
        diff = cur_val - prev_val
        pct = (diff / prev_val) * 100
        period_type = "전주" if is_weekly_view else "전월"
        if diff > 0:
            color = "#0284c7" if is_positive_good else "#dc2626"
            return f"<span style='color:{color}; font-size:11.5px; font-weight:800;'>▲ +{diff:.1f} (+{pct:.1f}% vs {period_type})</span>"
        elif diff < 0:
            color = "#16a34a" if is_positive_good else "#16a34a"
            return f"<span style='color:{color}; font-size:11.5px; font-weight:800;'>▼ {diff:.1f} ({pct:.1f}% vs {period_type})</span>"
        else:
            return f"<span style='color:#94a3b8; font-size:11.5px; font-weight:600;'>- 0.0% ({period_type} 동일)</span>"

    d_hours_badge = get_delta_badge(tot_hours, prev_tot_hours, is_positive_good=True)
    d_cnt_badge = get_delta_badge(tot_cnt, prev_tot_cnt, is_positive_good=True)
    d_clients_badge = get_delta_badge(tot_clients, prev_tot_clients, is_positive_good=True)
    d_avg_badge = get_delta_badge(avg_hours_per_worker, prev_avg_hours, is_positive_good=True)

    # =========================================================================
    # 1. 🏛️ 핵심 실적 5초 펄스 카드 (4대 핵심 지표 with MoM/WoW Delta)
    # =========================================================================
    pulse_cards_html = f"""
    <div style="display: flex; gap: 14px; margin-bottom: 20px; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 170px; background: #ffffff; border: 1px solid #e1e4e8; border-top: 5px solid #005073; border-radius: 10px; padding: 16px 18px; box-shadow: 0 2px 8px rgba(0,45,66,0.06);">
            <div style="font-size: 12px; font-weight: 700; color: #64748b; margin-bottom: 4px;">⏱️ 총 투입 공수</div>
            <div style="font-size: 26px; font-weight: 900; color: #005073; letter-spacing: -0.5px;">{tot_hours:,}h</div>
            <div style="margin-top: 6px;">{d_hours_badge}</div>
        </div>
        <div style="flex: 1; min-width: 170px; background: #ffffff; border: 1px solid #e1e4e8; border-top: 5px solid #0284c7; border-radius: 10px; padding: 16px 18px; box-shadow: 0 2px 8px rgba(0,45,66,0.06);">
            <div style="font-size: 12px; font-weight: 700; color: #64748b; margin-bottom: 4px;">👥 1인당 평균 공수</div>
            <div style="font-size: 26px; font-weight: 900; color: #0284c7; letter-spacing: -0.5px;">{avg_hours_per_worker:,}h</div>
            <div style="margin-top: 6px;">{d_avg_badge}</div>
        </div>
        <div style="flex: 1; min-width: 170px; background: #ffffff; border: 1px solid #e1e4e8; border-top: 5px solid #10b981; border-radius: 10px; padding: 16px 18px; box-shadow: 0 2px 8px rgba(0,45,66,0.06);">
            <div style="font-size: 12px; font-weight: 700; color: #64748b; margin-bottom: 4px;">🏢 지원 고객사 수</div>
            <div style="font-size: 26px; font-weight: 900; color: #10b981; letter-spacing: -0.5px;">{tot_clients}개사</div>
            <div style="margin-top: 6px;">{d_clients_badge}</div>
        </div>
        <div style="flex: 1; min-width: 170px; background: #ffffff; border: 1px solid #e1e4e8; border-top: 5px solid #f59e0b; border-radius: 10px; padding: 16px 18px; box-shadow: 0 2px 8px rgba(0,45,66,0.06);">
            <div style="font-size: 12px; font-weight: 700; color: #64748b; margin-bottom: 4px;">🎯 공수 예측 준수율</div>
            <div style="font-size: 26px; font-weight: 900; color: #f59e0b; letter-spacing: -0.5px;">{on_time_rate}%</div>
            <div style="margin-top: 6px; font-size: 11.5px; color: #64748b; font-weight: 600;">(초과 작업 {overdue_cnt}건)</div>
        </div>
    </div>
    """
    st.markdown(pulse_cards_html, unsafe_allow_html=True)

    # =========================================================================
    # 2. 📝 AI 경영 인사이트 & 액션 아이템 3단 브리핑 (화이트 테마)
    # =========================================================================
    client_agg = df_active.groupby("client_name")["actual_hours"].sum().sort_values(ascending=False)
    top_clients_text = []
    for c_rank, (c_name, c_h) in enumerate(client_agg.head(3).items(), 1):
        c_pct = round((c_h / tot_hours) * 100, 1) if tot_hours > 0 else 0
        top_clients_text.append(f"<b>{c_rank}위 {c_name}</b>({c_h}h, {c_pct}%)")
    top_clients_str = ", ".join(top_clients_text) if top_clients_text else "집계 중"

    # 야간/주말 공수 계산
    night_mask = df_active["is_night_work"] == True
    wknd_mask = df_active["is_weekend_work"] == True
    tot_night_hours = round(df_active[night_mask]["actual_hours"].sum(), 1) if "is_night_work" in df_active.columns else 0.0
    tot_wknd_hours = round(df_active[wknd_mask]["actual_hours"].sum(), 1) if "is_weekend_work" in df_active.columns else 0.0
    night_pct = round((tot_night_hours / tot_hours) * 100, 1) if tot_hours > 0 else 0.0
    wknd_pct = round((tot_wknd_hours / tot_hours) * 100, 1) if tot_hours > 0 else 0.0

    # 과중근무 리스크 분석
    danger_names = []
    caution_names = []
    safe_names = []
    danger_detail_map = {}
    caution_detail_map = {}

    def format_week_short(w_lbl: str) -> str:
        if not w_lbl:
            return ""
        base = str(w_lbl).split(" (")[0].strip()
        parts = base.split(" ")
        if len(parts) >= 2 and "-" in parts[0]:
            try:
                _, month = parts[0].split("-")
                return f"{int(month)}월 {parts[1]}"
            except Exception:
                return base
        return base

    worker_hours = df_active.groupby("worker_name")["actual_hours"].sum().to_dict() if ("worker_name" in df_active.columns and not df_active.empty) else {}
    if "worker_name" in df_active.columns and not df_active.empty:
        all_active_workers = list(df_active["worker_name"].dropna().unique())
        if "week_label" in df_active.columns:
            # 주 40h/52h 초과 산정 시 [교육] 및 [휴가] 구분은 법정 근로시간 합산에서 제외
            df_active_work = df_active[~df_active["log_type"].fillna("").astype(str).str.contains("교육|휴가")] if "log_type" in df_active.columns else df_active
            wk_agg = df_active_work.groupby(["worker_name", "week_label"])["actual_hours"].sum().reset_index()
            danger_rows = wk_agg[wk_agg["actual_hours"] > 52]
            caution_rows = wk_agg[(wk_agg["actual_hours"] > 40) & (wk_agg["actual_hours"] <= 52)]

            danger_workers = danger_rows["worker_name"].unique()
            caution_workers = caution_rows["worker_name"].unique()

            # 헬퍼 함수: 주차 라벨에서 정렬 튜플 추출 (예: '2026-08 2주차' -> (2026, 8, 2))
            def extract_week_sort_key(w_lbl: str):
                import re
                nums = [int(n) for n in re.findall(r'\d+', str(w_lbl))]
                return nums if nums else [9999]

            # 각 작업자별 가장 빠른 초과 발생 주차 정렬 키
            def get_earliest_week_key(w, sub_df):
                w_sub = sub_df[sub_df["worker_name"] == w]
                if not w_sub.empty:
                    keys = [extract_week_sort_key(wl) for wl in w_sub["week_label"]]
                    return min(keys)
                return [9999]

            # 🌟 빠른 주차가 위로 오도록 정렬 (1순위: 가장 빠른 발생 주차 오름차순, 2순위: 총 투입시간 내림차순)
            danger_names = sorted(
                list(danger_workers),
                key=lambda w: (get_earliest_week_key(w, danger_rows), -worker_hours.get(w, 0.0))
            )
            caution_names = sorted(
                [w for w in caution_workers if w not in danger_names],
                key=lambda w: (get_earliest_week_key(w, caution_rows), -worker_hours.get(w, 0.0))
            )

            # 주차 정보 표기 여부 (월간 전체 종합이거나 대상 주차가 복수인 경우)
            show_week_info = (not is_weekly_view) or (df_active["week_label"].nunique() > 1)

            for w in danger_names:
                # 괄호 안 주차 목록도 빠른 주차 순으로 정렬!
                sub_d = danger_rows[danger_rows["worker_name"] == w].copy()
                sub_d["_w_sort"] = sub_d["week_label"].apply(extract_week_sort_key)
                sub_d = sub_d.sort_values(by="_w_sort", ascending=True)
                if show_week_info:
                    wk_infos = [f"{format_week_short(r['week_label'])}: {r['actual_hours']:.1f}h" for _, r in sub_d.iterrows()]
                    danger_detail_map[w] = f"{w}({', '.join(wk_infos)})"
                else:
                    danger_detail_map[w] = f"{w}({worker_hours.get(w, 0.0):.1f}h)"

            for w in caution_names:
                # 괄호 안 주차 목록도 빠른 주차 순으로 정렬!
                sub_c = caution_rows[caution_rows["worker_name"] == w].copy()
                sub_c["_w_sort"] = sub_c["week_label"].apply(extract_week_sort_key)
                sub_c = sub_c.sort_values(by="_w_sort", ascending=True)
                if show_week_info:
                    wk_infos = [f"{format_week_short(r['week_label'])}: {r['actual_hours']:.1f}h" for _, r in sub_c.iterrows()]
                    caution_detail_map[w] = f"{w}({', '.join(wk_infos)})"
                else:
                    caution_detail_map[w] = f"{w}({worker_hours.get(w, 0.0):.1f}h)"

        safe_names = sorted([w for w in all_active_workers if w not in danger_names and w not in caution_names], key=lambda w: worker_hours.get(w, 0.0), reverse=True)

    danger_cnt = len(danger_names)
    caution_cnt = len(caution_names)
    safe_cnt = len(safe_names)

    top3_share = round((client_agg.head(3).sum() / tot_hours) * 100, 1) if tot_hours > 0 else 0.0

    danger_desc_inline = ', '.join([danger_detail_map.get(w, f"{w}({worker_hours.get(w, 0.0):.1f}h)") for w in danger_names])
    risk_status_html = "<span style='color:#16a34a; font-weight:800;'>🟢 법정 근로시간 안정 (주 52시간 초과 인원 없음)</span>" if danger_cnt == 0 else f"<span style='color:#dc2626; font-weight:800;'>🚨 주 52시간 초과 주의 ({danger_cnt}명: {danger_desc_inline})</span>"

    # ----------------------------------------------------
    # 🌟 다차원 팩트 추출(2번) + AI 심층 분석(1번) 결합 브리핑 생성
    # ----------------------------------------------------
    try:
        import importlib
        import src.services.ai_briefing_service as ai_srv
        importlib.reload(ai_srv)
        from src.services.ai_briefing_service import FactExtractor, AIBriefingService
    except Exception:
        pass

    facts = FactExtractor.extract_facts(df_active, prev_df, selected_team, current_period_label)

    b_col1, b_col2 = st.columns([4.2, 0.8])
    with b_col1:
        st.markdown(f"""
        <div style="display: flex; align-items: center; justify-content: space-between; height: 100%; min-height: 42px; padding-top: 6px;">
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                <span style="font-size: 16.5px; font-weight: 800; color: #002d42; letter-spacing: -0.3px;">📑 업무 실적 핵심 요약 브리핑 & 액션 아이템</span>
                <span style="font-size: 12px; color: #0284c7; background: #e0f2fe; padding: 2px 8px; border-radius: 4px; font-weight: 700;">조회 기준: {current_period_label}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with b_col2:
        st.markdown(
            """
            <style>
            div.st-key-btn_refresh_ai_briefing button {
                background-color: #004060 !important;
                background: linear-gradient(135deg, #002d42 0%, #005073 100%) !important;
                color: #FFFFFF !important;
                border: 1px solid rgba(255, 255, 255, 0.3) !important;
                border-radius: 6px !important;
                font-size: 13px !important;
                font-weight: 800 !important;
                height: 38px !important;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25) !important;
                transition: all 0.2s ease !important;
            }
            div.st-key-btn_refresh_ai_briefing button p,
            div.st-key-btn_refresh_ai_briefing button span {
                color: #FFFFFF !important;
                font-weight: 800 !important;
                font-size: 13px !important;
                letter-spacing: -0.2px !important;
            }
            div.st-key-btn_refresh_ai_briefing button:hover {
                background-color: #00608a !important;
                background: linear-gradient(135deg, #004060 0%, #0284c7 100%) !important;
                border-color: #38bdf8 !important;
                color: #FFFFFF !important;
                box-shadow: 0 4px 12px rgba(2, 132, 199, 0.45) !important;
                transform: translateY(-1px) !important;
            }
            div.st-key-btn_refresh_ai_briefing button:hover p,
            div.st-key-btn_refresh_ai_briefing button:hover span {
                color: #FFFFFF !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        # 🔑 Gemini API 키 감지 (Streamlit Secrets / 환경변수)
        gemini_api_key = ""
        try:
            if hasattr(st, "secrets"):
                gemini_api_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
        except Exception:
            pass
        if not gemini_api_key:
            gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if gemini_api_key:
            os.environ["GEMINI_API_KEY"] = gemini_api_key

        re_analyze = st.button("🔄 AI 재분석", use_container_width=True, key="btn_refresh_ai_briefing", help="클릭 시 Gemini AI API를 호출하여 심층 컨설팅 브리핑을 생성합니다 (토큰 소모).")

    # ★ 옵션 2 토큰 절약 모드: [🔄 AI 재분석] 버튼을 클릭했을 때만 Gemini API 호출 (토큰 소모) ★
    if re_analyze:
        with st.spinner("✨ Gemini AI가 현장 데이터를 심층 분석 중입니다 (API 토큰 소모)..."):
            ai_briefing = AIBriefingService.generate_briefing(facts, force_refresh=True, api_key=gemini_api_key, allow_ai_call=True)
    else:
        # 평소 조회 변경 시: 토큰 소모 없이 팩트 기반 규칙 엔진 또는 이전 Gemini 캐시 표출 (0초 딜레이)
        ai_briefing = AIBriefingService.generate_briefing(facts, force_refresh=False, api_key=gemini_api_key, allow_ai_call=False)

    briefing_source = ai_briefing.get("source", "")
    is_gemini = "Gemini" in briefing_source

    if is_gemini:
        badge_html = '<span style="font-size: 11.5px; color: #15803d; background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border: 1.5px solid #86efac; padding: 3px 12px; border-radius: 20px; font-weight: 800; box-shadow: 0 1px 3px rgba(34,197,94,0.1);">✨ Gemini AI 심층 분석 완료</span>'
        notice_banner_html = ""
    else:
        badge_html = '<span style="font-size: 11px; color: #475569; background: #f1f5f9; border: 1px solid #cbd5e1; padding: 3px 10px; border-radius: 20px; font-weight: 700;">📊 팩트 기반 규칙 브리핑 (토큰 0 소모)</span>'
        notice_banner_html = '<div style="margin-bottom: 14px; background: linear-gradient(90deg, #f0f9ff 0%, #e0f2fe 100%); border: 1.5px dashed #0284c7; border-radius: 8px; padding: 10px 16px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;"><div style="display: flex; align-items: center; gap: 8px;"><span style="font-size: 16px;">💡</span><span style="font-size: 12.5px; color: #0369a1; font-weight: 700;">현재는 <b>토큰 소모가 없는 팩트 규칙 분석</b> 상태입니다. Gemini의 심층 원인 진단과 컨설팅 제언이 필요하시면 우측 상단의 <b>[🔄 AI 재분석]</b> 버튼을 눌러주세요.</span></div><span style="font-size: 11px; color: #0284c7; background: #ffffff; border: 1px solid #bae6fd; padding: 3px 8px; border-radius: 4px; font-weight: 800; white-space: nowrap;">⚡ 클릭 시 토큰 소모</span></div>'

    briefing_overview = AIBriefingService.clean_briefing_text(ai_briefing.get('overview', ''))
    briefing_risks = AIBriefingService.clean_briefing_text(ai_briefing.get('risks', ''))
    briefing_recomms = AIBriefingService.clean_briefing_text(ai_briefing.get('recommendations', ''))

    briefing_html = f"""<div style="background: #ffffff; border: 1.5px solid #005f8a; border-left: 6px solid #005073; border-radius: 12px; padding: 18px 24px; margin-bottom: 24px; box-shadow: 0 4px 16px rgba(0, 45, 66, 0.06);">
<div style="margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; padding-bottom: 10px; border-bottom: 1px solid #f1f5f9;">
<div style="display: flex; align-items: center; gap: 8px;">
<span style="font-size: 15px; font-weight: 800; color: #002d42;">📋 핵심 운영 진단 & 전략 지침</span>
</div>
{badge_html}
</div>
{notice_banner_html}
<div style="font-size: 13.5px; color: #1e293b; line-height: 1.85;">
<div style="margin-bottom: 10px; background: #f8fafc; padding: 12px 16px; border-radius: 8px; border-left: 3.5px solid #0284c7;">
📌 <b>핵심 변화 & 집중 요인</b>: {briefing_overview}
</div>
<div style="margin-bottom: 10px; background: #f8fafc; padding: 12px 16px; border-radius: 8px; border-left: 3.5px solid #f59e0b;">
⚠️ <b>현장 리스크 & 지연 진단</b>: {briefing_risks}
</div>
<div style="background: #f8fafc; padding: 12px 16px; border-radius: 8px; border-left: 3.5px solid #10b981;">
💡 <b>차기 운영 전략 & 액션 플랜</b>: {briefing_recomms}
</div>
</div>
</div>"""
    st.markdown(briefing_html, unsafe_allow_html=True)

    # 🌟 화면 서머리 컨텍스트 실시간 저장 (이메일 발송 팝업 시 화면 내용 100% 일치 연동)
    st.session_state["exec_summary_context"] = {
        "current_period_label": current_period_label,
        "selected_team": selected_team,
        "df_active": df_active,
        "prev_df": prev_df,
        "ai_briefing": ai_briefing,
        "available_weeks": available_weeks,
        "df_scope": df_scope,
        "team_mappings": team_mappings
    }

    # =========================================================================
    # 3. 📅 주차별 핵심 실적 종합 비교표 (Weekly Breakdown Matrix)
    # =========================================================================
    if len(available_weeks) > 1:
        st.markdown("#### 📅 1. 주차별 핵심 실적 종합 비교표 (Weekly Matrix)")
        st.caption("선택된 월 내의 모든 주차별 공수, 인원, 주요 고객사 및 근무 건전성 흐름을 비교합니다.")
        weekly_matrix_rows = []
        for w_label in available_weeks:
            sub_w = df_scope[df_scope["week_label"] == w_label]
            if sub_w.empty:
                continue
            w_hours = round(sub_w["actual_hours"].sum(), 1)
            w_workers = sub_w["worker_name"].nunique()
            w_cnt = len(sub_w)
            w_avg = round(w_hours / w_workers, 1) if w_workers > 0 else 0.0
            w_night = int(sub_w["is_night_work"].sum()) if "is_night_work" in sub_w.columns else 0
            w_wknd = int(sub_w["is_weekend_work"].sum()) if "is_weekend_work" in sub_w.columns else 0
            
            w_top_c = sub_w.groupby("client_name")["actual_hours"].sum().sort_values(ascending=False).head(2)
            w_top_c_str = ", ".join([f"{cn}({round(ch,1)}h)" for cn, ch in w_top_c.items()]) if not w_top_c.empty else "-"
            
            w_agg = sub_w.groupby("worker_name")["actual_hours"].sum()
            w_danger = int((w_agg > 52).sum())
            w_status = f"🚨 52h 초과({w_danger}명)" if w_danger > 0 else "🟢 안정"

            weekly_matrix_rows.append({
                "주차": w_label,
                "투입 인원": f"{w_workers}명",
                "작업 건수": f"{w_cnt:,}건",
                "총 투입공수": f"{w_hours:,}h",
                "1인당 평균": f"{w_avg}h",
                "주요 지원 고객사 Top 2": w_top_c_str,
                "🌙 야간": f"{w_night}건",
                "🏖️ 주말": f"{w_wknd}건",
                "근무 건전성": w_status
            })
        if weekly_matrix_rows:
            st.dataframe(pd.DataFrame(weekly_matrix_rows), use_container_width=True, hide_index=True)

        st.write("")
        st.divider()

    # =========================================================================
    # 4. ⚖️ 인력 운영 건전성 & 법정 근로시간 거버넌스 (Workforce Governance)
    # =========================================================================
    st.markdown("#### ⚖️ 2. 인력 운영 건전성 & 법정 근로시간 거버넌스")
    st.caption("주 52시간 근로시간 규정 준수 현황과 야간·주말 비정규 투입 비중을 진단합니다.")

    danger_str_list = [danger_detail_map.get(w, f"{w}({worker_hours.get(w, 0.0):.1f}h)") for w in danger_names]
    caution_str_list = [caution_detail_map.get(w, f"{w}({worker_hours.get(w, 0.0):.1f}h)") for w in caution_names]
    safe_str_list = [f"{w}({worker_hours.get(w, 0.0):.1f}h)" for w in safe_names]

    def format_card_lines(str_list: list, empty_msg: str) -> str:
        if not str_list:
            return empty_msg
        return "".join([f"<div style='margin-top: 4px; line-height: 1.6;'>{item}</div>" for item in str_list])

    danger_text = format_card_lines(danger_str_list, '초과 인원 없음 (안전)')
    caution_text = format_card_lines(caution_str_list, '주의 대상자 없음 (안전)')
    if len(safe_str_list) <= 5:
        safe_text = format_card_lines(safe_str_list, '해당 인원 없음')
    else:
        safe_text = ', '.join(safe_str_list) if safe_str_list else '해당 인원 없음'

    st.markdown(f"""
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; align-items: stretch; margin-top: 4px;">
        <div style="display: flex; flex-direction: column; justify-content: flex-start; background: #ffffff; border: 1.5px solid {'#fca5a5' if danger_cnt > 0 else '#e2e8f0'}; border-left: 4px solid {'#dc2626' if danger_cnt > 0 else '#16a34a'}; border-radius: 8px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); height: 100%; box-sizing: border-box;">
            <div style="font-size: 12px; font-weight: 700; color: #64748b;">🚨 주 52시간 초과 위험군</div>
            <div style="font-size: 22px; font-weight: 900; color: {'#dc2626' if danger_cnt > 0 else '#16a34a'}; margin-top: 2px;">{danger_cnt}명</div>
            <div style="font-size: 11.5px; color: {'#dc2626' if danger_cnt > 0 else '#64748b'}; margin-top: 4px; word-break: break-word; font-weight: 600; line-height: 1.5;">{danger_text}</div>
        </div>
        <div style="display: flex; flex-direction: column; justify-content: flex-start; background: #ffffff; border: 1.5px solid {'#fde68a' if caution_cnt > 0 else '#e2e8f0'}; border-left: 4px solid {'#d97706' if caution_cnt > 0 else '#16a34a'}; border-radius: 8px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); height: 100%; box-sizing: border-box;">
            <div style="font-size: 12px; font-weight: 700; color: #64748b;">⚠️ 주 40~52시간 관리 주의군</div>
            <div style="font-size: 22px; font-weight: 900; color: {'#d97706' if caution_cnt > 0 else '#16a34a'}; margin-top: 2px;">{caution_cnt}명</div>
            <div style="font-size: 11.5px; color: {'#d97706' if caution_cnt > 0 else '#64748b'}; margin-top: 4px; word-break: break-word; font-weight: 600; line-height: 1.5;">{caution_text}</div>
        </div>
        <div style="display: flex; flex-direction: column; justify-content: flex-start; background: #ffffff; border: 1.5px solid #e2e8f0; border-left: 4px solid #16a34a; border-radius: 8px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); height: 100%; box-sizing: border-box;">
            <div style="font-size: 12px; font-weight: 700; color: #64748b;">🟢 안정적 근로시간 준수군</div>
            <div style="font-size: 22px; font-weight: 900; color: #16a34a; margin-top: 2px;">{safe_cnt}명</div>
            <div style="font-size: 11.5px; color: #16a34a; margin-top: 4px; word-break: break-word; font-weight: 600; line-height: 1.5;">{safe_text}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.write("")
    st.divider()

    # =========================================================================
    # 3. 🏢 전체 고객사 포트폴리오 파레토 분석 & 주요 집계표
    # =========================================================================
    st.markdown("#### 🏢 3. 전체 고객사별 공수 투입 및 파레토 분석")
    
    # 전체 고객사 파레토 차트 렌더링
    all_clients = client_agg.reset_index()
    all_clients.columns = ["client_name", "actual_hours"]
    all_clients["cum_pct"] = (all_clients["actual_hours"].cumsum() / tot_hours) * 100 if tot_hours > 0 else 0

    fig_pareto = go.Figure()
    fig_pareto.add_trace(go.Bar(
        x=all_clients["client_name"],
        y=all_clients["actual_hours"],
        name="투입 공수(h)",
        marker=dict(color="#005073", line=dict(color="#002d42", width=1)),
        text=[f"{h:.1f}h" for h in all_clients["actual_hours"]],
        textposition="auto"
    ))
    fig_pareto.add_trace(go.Scatter(
        x=all_clients["client_name"],
        y=all_clients["cum_pct"],
        name="누적 점유율(%)",
        yaxis="y2",
        mode="lines+markers+text",
        line=dict(color="#ea580c", width=2.5),
        marker=dict(size=7, color="#ea580c"),
        text=[f"{p:.1f}%" for p in all_clients["cum_pct"]],
        textposition="top center"
    ))
    fig_pareto.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family="Pretendard, -apple-system, sans-serif", color="#002d42", size=12),
        height=360,
        margin=dict(l=20, r=20, t=35, b=30),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color="#002d42", size=12, family="Pretendard"),
            bgcolor="rgba(255, 255, 255, 0.95)",
            bordercolor="#e2e8f0",
            borderwidth=1
        ),
        yaxis=dict(
            title=dict(text="투입 공수 (시간)", font=dict(color="#005073", size=12, family="Pretendard")),
            tickfont=dict(color="#005073", size=11, family="Pretendard"),
            gridcolor="#f1f5f9",
            zerolinecolor="#cbd5e1"
        ),
        yaxis2=dict(
            title=dict(text="누적 점유율 (%)", font=dict(color="#ea580c", size=12, family="Pretendard")),
            tickfont=dict(color="#ea580c", size=11, family="Pretendard"),
            overlaying="y",
            side="right",
            range=[0, 105],
            showgrid=False
        ),
        xaxis=dict(
            tickfont=dict(color="#002d42", size=12, family="Pretendard"),
            linecolor="#cbd5e1"
        ),
        hovermode="x unified"
    )
    st.plotly_chart(fig_pareto, use_container_width=True)

    # 💡 고객사 공수 집중도 핵심 인사이트 동적 산출 (그래프 바로 아래 / 표 바로 위 배치)
    cum_80_idx = len(all_clients)
    for idx, pct in enumerate(all_clients["cum_pct"]):
        if pct >= 80.0:
            cum_80_idx = idx + 1
            break

    if cum_80_idx <= 3:
        top_pareto_names = ", ".join(all_clients.iloc[:cum_80_idx]["client_name"].tolist())
    else:
        top_3_names = ", ".join(all_clients.iloc[:3]["client_name"].tolist())
        top_pareto_names = f"{top_3_names} 외 {cum_80_idx - 3}개사"

    top_pareto_pct = all_clients.iloc[cum_80_idx - 1]["cum_pct"] if not all_clients.empty else 0.0

    pareto_insight_html = f"""
    <div style="background: #f0fdf4; border: 1.5px solid #86efac; border-left: 5px solid #16a34a; border-radius: 8px; padding: 13px 18px; margin-top: 6px; margin-bottom: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.03);">
        <div style="font-size: 13.5px; color: #14532d; font-weight: 700; line-height: 1.65;">
            💡 <b>고객사 공수 집중도 분석</b>: 
            <b>{current_period_label}</b> 기준 지원 고객사는 총 <b>{tot_clients}개사</b>이며, 
            전체 업무 공수(<b>{tot_hours:,}시간</b>)의 <b>{top_pareto_pct:.1f}%</b>가 
            상위 <b>{cum_80_idx}개 고객사({top_pareto_names})</b>에 집중 투입되었습니다.
        </div>
    </div>
    """
    st.markdown(pareto_insight_html, unsafe_allow_html=True)

    # ⚠️ 단일 고객사 30% 초과 편중 워닝 감지
    over_30_clients = [(c_n, c_h, (c_h / tot_hours) * 100) for c_n, c_h in client_agg.items() if tot_hours > 0 and ((c_h / tot_hours) * 100) >= 30.0]
    if over_30_clients:
        over_30_details = ", ".join([f"<b>{cn}</b>({pct:.1f}%, {ch:,}h)" for cn, ch, pct in over_30_clients])
        warning_html = f"""
        <div style="background: #fffbeb; border: 1.5px solid #fcd34d; border-left: 5px solid #f59e0b; border-radius: 8px; padding: 12px 18px; margin-top: 0px; margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
            <div style="font-size: 13.5px; color: #b45309; font-weight: 700; line-height: 1.6;">
                ⚠️ <b>고객사 의존도 주의 경보</b>: 
                단일 고객사 {over_30_details}의 비중이 전체의 <b>30% 이상</b>을 차지하여 특정 고객사 업무 편중 리스크가 감지되었습니다. (전담 엔지니어 피로도 관리 및 대체 백업 인력 편성 권장)
            </div>
        </div>
        """
        st.markdown(warning_html, unsafe_allow_html=True)

    # 🏢 고객사별 단일 GroupBy 사전 집계 (O(N) 1회 처리)
    client_grp = df_active.groupby("client_name")
    c_w_counts = client_grp["worker_name"].nunique().to_dict()
    c_counts = client_grp.size().to_dict()
    c_tasks = client_grp["task_description"].agg(lambda s: ", ".join(s.dropna().unique()[:2])).to_dict()

    client_table_rows = [
        {
            "순위": f"{c_rank}위",
            "고객사명": c_name,
            "투입 인원": f"{c_w_counts.get(c_name, 0)}명",
            "작업 건수": f"{c_counts.get(c_name, 0)}건",
            "총 투입공수": f"{round(c_h, 1)}h",
            "공수 비중": f"{round((c_h / tot_hours) * 100, 1) if tot_hours > 0 else 0}%",
            "주요 지원 작업": c_tasks.get(c_name, "")
        }
        for c_rank, (c_name, c_h) in enumerate(client_agg.items(), 1)
    ]

    if client_table_rows:
        st.dataframe(pd.DataFrame(client_table_rows), use_container_width=True, hide_index=True)

    st.write("")
    st.divider()

    # =========================================================================
    # 4. 👥 전체 팀원별 공수 투입 현황 (단일 GroupBy 사전 집계 최적화)
    # =========================================================================
    st.markdown("#### 👥 4. 전체 팀원별 공수 투입 현황")
    if not df_active.empty:
        worker_agg = df_active.groupby("worker_name")["actual_hours"].sum().sort_values(ascending=False)
        worker_grp = df_active.groupby("worker_name")
        w_counts = worker_grp.size().to_dict()
        w_first_teams = worker_grp["worker_team"].first().to_dict() if "worker_team" in df_active.columns else {}
        w_first_titles = worker_grp["worker_title"].first().to_dict() if "worker_title" in df_active.columns else {}
        
        # 작업자별 고객사 Top2 단일 집계
        wc_agg = df_active.groupby(["worker_name", "client_name"])["actual_hours"].sum().reset_index()
        wc_agg = wc_agg.sort_values(by=["worker_name", "actual_hours"], ascending=[True, False])
        top_c_by_worker = {}
        for w_name, grp in wc_agg.groupby("worker_name"):
            top2 = grp.head(2)
            top_c_by_worker[w_name] = ", ".join([f"{r['client_name']}({round(r['actual_hours'],1)}h)" for _, r in top2.iterrows()])

        all_worker_rows = [
            {
                "순위": f"{rank}위",
                "팀원명": w_name,
                "소속팀": w_first_teams.get(w_name) or team_mappings.get(w_name, UNASSIGNED_TEAM),
                "직급": w_first_titles.get(w_name, ""),
                "작업 건수": f"{w_counts.get(w_name, 0):,}건",
                "총 투입공수": f"{round(w_hours, 1)}h",
                "주요 지원 고객사": top_c_by_worker.get(w_name, "-")
            }
            for rank, (w_name, w_hours) in enumerate(worker_agg.items(), 1)
        ]
        if all_worker_rows:
            st.dataframe(pd.DataFrame(all_worker_rows), use_container_width=True, hide_index=True)

    st.write("")
    st.divider()

    # =========================================================================
    # 5. 📈 주차별 공수 변동 추이 & 부서별 종합 집계표 (구 4번에서 위치 이동)
    # =========================================================================
    st.markdown("#### 📈 5. 주차별 공수 변동 추이 & 부서별 종합 집계표")

    df_teams = df_active.copy()
    if "worker_team" in df_teams.columns:
        df_teams["worker_team"] = df_teams["worker_team"].fillna(df_teams["worker_name"].map(team_mappings)).fillna(UNASSIGNED_TEAM)
    else:
        df_teams["worker_team"] = df_teams["worker_name"].map(team_mappings).fillna(UNASSIGNED_TEAM)

    if "week_label" in df_teams.columns and not df_teams["week_label"].dropna().empty:
        wk_trend = df_teams.groupby(["week_label", "worker_team"])["actual_hours"].sum().reset_index()
        fig_trend = px.bar(
            wk_trend,
            x="week_label",
            y="actual_hours",
            color="worker_team",
            color_discrete_sequence=["#005073", "#0284c7", "#10b981", "#f59e0b", "#8b5cf6", "#64748b"],
            labels={"week_label": "주차", "actual_hours": "투입 공수(시간)", "worker_team": "소속팀"}
        )
        fig_trend.update_layout(
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font=dict(family="Pretendard, -apple-system, sans-serif", color="#002d42", size=12),
            height=300,
            margin=dict(l=15, r=15, t=30, b=20),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(color="#002d42", size=11.5, family="Pretendard"),
                bgcolor="rgba(255, 255, 255, 0.95)"
            ),
            yaxis=dict(
                title=dict(text="투입 공수(h)", font=dict(color="#002d42", size=12, family="Pretendard")),
                tickfont=dict(color="#002d42", size=11, family="Pretendard"),
                gridcolor="#f1f5f9"
            ),
            xaxis=dict(
                title=None,
                tickfont=dict(color="#002d42", size=12, family="Pretendard"),
                linecolor="#cbd5e1"
            )
        )
        st.plotly_chart(fig_trend, use_container_width=True)

    team_table_rows = []
    for t_name in get_all_teams_safe() + [UNASSIGNED_TEAM]:
        sub_t_df = df_teams[df_teams["worker_team"] == t_name]
        if sub_t_df.empty:
            continue
        t_w_cnt = sub_t_df["worker_name"].nunique()
        t_cnt = len(sub_t_df)
        t_h = round(sub_t_df["actual_hours"].sum(), 1)
        t_avg_h = round(t_h / t_w_cnt, 1) if t_w_cnt > 0 else 0
        t_night = int(sub_t_df["is_night_work"].sum()) if "is_night_work" in sub_t_df.columns else 0
        t_weekend = int(sub_t_df["is_weekend_work"].sum()) if "is_weekend_work" in sub_t_df.columns else 0
        t_share = round((t_h / tot_hours) * 100, 1) if tot_hours > 0 else 0

        team_table_rows.append({
            "부서/팀명": t_name,
            "투입 인원": f"{t_w_cnt}명",
            "총 작업건수": f"{t_cnt:,}건",
            "총 공수": f"{t_h:,}h",
            "1인당 평균공수": f"{t_avg_h}h",
            "전체 비중": f"{t_share}%",
            "🌙 야간작업": f"{t_night}건",
            "🏖️ 주말작업": f"{t_weekend}건"
        })

    if team_table_rows:
        st.dataframe(pd.DataFrame(team_table_rows), use_container_width=True, hide_index=True)





def render_summary_view(df: pd.DataFrame, df_raw: pd.DataFrame, selected_team: str, team_mappings: dict, month_desc: str = ""):
    """📊 Summary (업무 실적 요약) 메인 뷰"""
    render_work_summary_tab(df, df_raw, selected_team, team_mappings, month_desc)


# 하위 호환성 별칭
render_executive_summary_tab = render_work_summary_tab
