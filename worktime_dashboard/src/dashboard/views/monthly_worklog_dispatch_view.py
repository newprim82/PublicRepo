# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List

from ...services.monthly_worklog_service import MonthlyWorklogService
from ...services.team_service import TeamService
from ..common.ui_helpers import get_current_kst_time


def render_monthly_worklog_dispatch_view():
    """
    📑 [팀 전월 엑셀 원장 정기 발송] 메인 뷰 (시스템 관리 하위 메뉴)
    - 매달 1일 08:00에 기술1팀 인원 전체에 대한 전월 카톡/아웃룩 엑셀 원장을 팀메일로 정기 전달
    - 기본 팀메일: GE101@sangsanginworld.co.kr (수정 및 저장 가능)
    - 즉시 테스트 발송 및 엑셀 원장(.xlsx) 브라우저 다운로드 제공
    - 팀 전월 엑셀 원장 전용 독립 발송 이력 제공 (서머리 이력과 100% 분리)
    """
    st.markdown("""
    <style>
    /* ☀️ 흰색 바탕 100% 고대비 블랙 텍스트 표준 스타일 */
    .monthly-hero {
        background: #ffffff !important;
        border: 1.5px solid #0284c7 !important;
        border-left: 6px solid #0284c7 !important;
        border-radius: 10px !important;
        padding: 18px 24px !important;
        margin-bottom: 22px !important;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06) !important;
    }
    .monthly-hero-title {
        font-size: 21px !important;
        font-weight: 900 !important;
        color: #000000 !important;
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
        margin-bottom: 6px !important;
    }
    .monthly-hero-desc {
        font-size: 13.5px !important;
        color: #000000 !important;
        font-weight: 500 !important;
        line-height: 1.6 !important;
    }
    .metric-card-box {
        background: #ffffff !important;
        border: 1.5px solid #cbd5e1 !important;
        border-radius: 8px !important;
        padding: 14px 16px !important;
        text-align: center !important;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05) !important;
    }
    .metric-card-title {
        font-size: 12px !important;
        font-weight: 800 !important;
        color: #000000 !important;
    }
    .metric-card-value {
        font-size: 23px !important;
        font-weight: 900 !important;
        color: #000000 !important;
        margin-top: 4px !important;
    }
    /* 라벨 텍스트: 선명한 블랙 강제 */
    label,
    div[data-testid="stWidgetLabel"] p,
    div[data-testid="stWidgetLabel"] span,
    div[data-testid="stWidgetLabel"] * {
        color: #000000 !important;
        font-weight: 800 !important;
        font-size: 13.5px !important;
    }
    /* 셀렉트박스 & 인풋창 */
    div[data-baseweb="input"],
    div[data-baseweb="base-input"],
    div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        background: #ffffff !important;
        border: 1.5px solid #94a3b8 !important;
        border-radius: 6px !important;
    }
    div[data-baseweb="input"] input,
    div[data-baseweb="base-input"] input,
    div[data-baseweb="select"] span,
    div[data-baseweb="select"] div,
    div[data-baseweb="select"] * {
        color: #000000 !important;
        font-weight: 700 !important;
    }
    div[data-baseweb="select"] svg {
        fill: #000000 !important;
        color: #000000 !important;
    }
    /* 토글 스위치 */
    div[data-testid="stToggle"] label span {
        color: #000000 !important;
        font-weight: 800 !important;
    }
    /* 다운로드 버튼 */
    div.stDownloadButton > button {
        background-color: #0284c7 !important;
        border: 1px solid #0369a1 !important;
        border-radius: 6px !important;
        color: #ffffff !important;
        font-weight: 800 !important;
        font-size: 13.5px !important;
    }
    div.stDownloadButton > button * {
        color: #ffffff !important;
        font-weight: 800 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # 1. Hero Section
    st.markdown("""
    <div class="monthly-hero">
        <div class="monthly-hero-title">
            <span>📑</span>
            <span>팀 전월 엑셀 원장 정기 발송 관리</span>
        </div>
        <div class="monthly-hero-desc">
            매달 1일 오전 08:00, <b>기술1팀 인원 전체에 대한 전월 카카오톡 업무 지원 기록과 아웃룩 캘린더 일정 원장</b>을 다중 시트 엑셀(.xlsx)로 자동 생성하여 지정된 팀 대표 이메일로 전송합니다.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 기본 전월 산출
    prev_month_default = MonthlyWorklogService.get_previous_month()

    # 2. 팀 설정 및 즉시 발송 제어 그리드
    col_cfg, col_action = st.columns([1.1, 0.9], gap="large")

    all_teams = TeamService.get_all_teams()
    if not all_teams:
        all_teams = ["기술 1팀"]
    default_team_idx = all_teams.index("기술 1팀") if "기술 1팀" in all_teams else 0

    with col_cfg:
        st.markdown("<h4 style='color: #000000; font-weight: 900;'>⚙️ 팀별 정기 발송 설정</h4>", unsafe_allow_html=True)
        selected_team = st.selectbox(
            "🏢 대상 팀 선택:",
            options=all_teams,
            index=default_team_idx,
            key="mw_select_team"
        )

        team_cfg = MonthlyWorklogService.get_team_config(selected_team)
        current_email = team_cfg.get("team_email", "GE101@sangsanginworld.co.kr" if "1" in selected_team else "")
        current_active = team_cfg.get("is_active", True)
        current_cron = team_cfg.get("schedule_cron", "매달 1일 08:00")

        input_email = st.text_input(
            "📬 팀 대표 수신 이메일 주소:",
            value=current_email,
            key="mw_input_team_email",
            help="해당 팀의 대표 메일 주소입니다. (예: GE101@sangsanginworld.co.kr)"
        )

        sub_c1, sub_c2 = st.columns(2)
        with sub_c1:
            st.text_input("⏳ 발송 스케줄:", value=current_cron, disabled=True, key="mw_cron_disp")
        with sub_c2:
            is_active_toggle = st.toggle("🟢 자동 발송 활성화", value=current_active, key="mw_active_toggle")

        if st.button("💾 정기 발송 설정 저장", type="primary", use_container_width=True, key="btn_save_team_cfg"):
            MonthlyWorklogService.save_team_config(
                team_name=selected_team,
                team_email=input_email,
                is_active=is_active_toggle,
                note=f"{selected_team} 전월 업무 원장 정기 발송"
            )
            st.toast(f"✅ [{selected_team}] 정기 발송 설정이 성공적으로 저장되었습니다!", icon="💾")
            st.rerun()

    with col_action:
        st.markdown("<h4 style='color: #000000; font-weight: 900;'>🚀 즉시 테스트 발송 & 원장 다운로드</h4>", unsafe_allow_html=True)
        
        # 발송 대상 월 선택 (기본: 전월)
        target_month = st.selectbox(
            "📅 발송 대상 월 (기본: 전월):",
            options=[prev_month_default, get_current_kst_time().strftime("%Y-%m")],
            index=0,
            key="mw_select_month"
        )

        # 실시간 데이터 로드
        with st.spinner("데이터 집계 중..."):
            team_df = MonthlyWorklogService.get_team_monthly_data(selected_team, target_month)

        tot_rows = len(team_df)
        tot_hours = round(team_df["actual_hours"].sum(), 1) if "actual_hours" in team_df.columns else 0.0
        kakao_cnt = len(team_df[~team_df["is_outlook"]]) if "is_outlook" in team_df.columns else tot_rows
        outlook_cnt = len(team_df[team_df["is_outlook"]]) if "is_outlook" in team_df.columns else 0

        # 요약 미니 카드 (흰색 바탕 + 고대비 블랙 수치)
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.markdown(f"""
            <div class="metric-card-box">
                <div class="metric-card-title">총 업무/일정</div>
                <div class="metric-card-value" style="color: #000000 !important;">{tot_rows:,}<span style="font-size: 13px; font-weight: 700; color: #000000 !important;">건</span></div>
            </div>
            """, unsafe_allow_html=True)
        with mc2:
            st.markdown(f"""
            <div class="metric-card-box">
                <div class="metric-card-title">총 투입 공수</div>
                <div class="metric-card-value" style="color: #000000 !important;">{tot_hours:,.1f}<span style="font-size: 13px; font-weight: 700; color: #000000 !important;">h</span></div>
            </div>
            """, unsafe_allow_html=True)
        with mc3:
            st.markdown(f"""
            <div class="metric-card-box">
                <div class="metric-card-title">카톡 / 아웃룩</div>
                <div class="metric-card-value" style="font-size: 17px !important; margin-top: 8px !important; color: #000000 !important;">{kakao_cnt} / {outlook_cnt}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        # 액션 버튼 2개
        btn_send_now = st.button("🚀 지금 즉시 팀 메일로 발송", type="primary", use_container_width=True, key="btn_send_now_team_report")
        if btn_send_now:
            if not input_email:
                st.error("수신 팀 메일 주소를 입력해주세요.")
            elif team_df.empty:
                st.warning(f"[{selected_team}] {target_month} 기간에 등록된 데이터가 없습니다.")
            else:
                with st.spinner(f"📧 [{selected_team}] {target_month} 전월 엑셀 원장 생성 및 메일 발송 중..."):
                    success, msg = MonthlyWorklogService.send_monthly_team_report(
                        team_name=selected_team,
                        recipient_email=input_email,
                        month_str=target_month,
                        dispatch_type="MANUAL_IMMEDIATE"
                    )
                    if success:
                        st.toast(msg, icon="✅")
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        if not team_df.empty:
            excel_bytes = MonthlyWorklogService.generate_monthly_worklog_excel(team_df, selected_team, target_month)
            clean_team_fn = selected_team.replace(" ", "")
            clean_m_fn = target_month.replace("-", "")
            st.download_button(
                label=f"📥 {selected_team} {target_month} 엑셀 원장(.xlsx) 다운로드",
                data=excel_bytes,
                file_name=f"{clean_team_fn}_{clean_m_fn}_전월_업무원장_통합리포트.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="btn_download_monthly_worklog"
            )

    st.markdown("<hr style='border: 0; border-top: 1px solid #cbd5e1; margin: 28px 0 20px 0;'>", unsafe_allow_html=True)

    # 3. 팀 전월 엑셀 원장 독립 발송 이력 (서머리 이력과 완전 분리)
    st.markdown(f"<h4 style='color: #000000; font-weight: 900;'>📜 [{selected_team}] 전월 엑셀 원장 최근 발송 이력</h4>", unsafe_allow_html=True)
    dedicated_logs = MonthlyWorklogService.get_recent_dispatches(team_name=selected_team, limit=10)

    if not dedicated_logs:
        st.markdown(
            f"""
            <div style="background: #ffffff; border: 1.5px dashed #cbd5e1; border-radius: 8px; padding: 18px; text-align: center; color: #475569; font-size: 13px; line-height: 1.6;">
                ⏳ 아직 발송된 <b>[{selected_team}]</b> 전월 엑셀 원장 이력이 없습니다.<br>
                <span style="font-size: 11.5px; color: #64748b;">위의 [🚀 지금 즉시 팀 메일로 발송] 버튼을 누르거나 매달 1일 08:00 자동 발송 시 여기에만 독립적으로 기록됩니다.</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        for item in dedicated_logs:
            d_type = item.get("dispatch_type", "MANUAL_IMMEDIATE")
            d_badge = '<span style="background:#0284c7; color:#ffffff; padding:2.5px 8px; border-radius:4px; font-size:11px; font-weight:800;">🚀 즉시 발송</span>' if "MANUAL" in d_type else '<span style="background:#16a34a; color:#ffffff; padding:2.5px 8px; border-radius:4px; font-size:11px; font-weight:800;">⏳ 정기 자동</span>'
            status = item.get("status", "SUCCESS")
            status_html = '<span style="color:#15803d; font-weight:800; font-size:12px;">✅ 성공</span>' if status == "SUCCESS" else '<span style="color:#b91c1c; font-weight:800; font-size:12px;" title="' + str(item.get("error_message", "")) + '">❌ 실패</span>'
            dt_str = str(item.get("created_at", "")).replace("T", " ")
            short_dt = dt_str[:16] if len(dt_str) >= 16 else dt_str
            t_month = item.get("target_month", "")
            t_name = item.get("team_name", selected_team)
            rcpt = item.get("recipient_email", "")
            tot_rec = item.get("total_records", 0)
            tot_h = float(item.get("total_hours", 0.0) or 0.0)
            fn = item.get("excel_filename", "")

            st.markdown(f"""
            <div style="background: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 8px; padding: 13px 18px; margin-bottom: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.05);">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 9px; flex-wrap: wrap; gap: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        {d_badge}
                        <span style="color: #000000; font-weight: 800; font-size: 13.5px;">[{t_name}] {t_month} 전월 원장</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="color: #475569; font-size: 12px; font-weight: 600;">{short_dt}</span>
                        {status_html}
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; font-size: 12.5px;">
                    <div style="color: #000000; font-weight: 700;">
                        <span style="color: #0284c7;">✉️ 수신 팀메일:</span> {rcpt}
                    </div>
                    <div style="color: #475569; font-weight: 600;">
                        📊 실적: <b style="color: #000000;">{tot_rec:,}건</b> ({tot_h:,.1f}h) | 📎 첨부: <span style="color: #0284c7;">{fn}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
