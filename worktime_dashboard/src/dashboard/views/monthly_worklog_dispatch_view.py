# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List

from ...services.monthly_worklog_service import MonthlyWorklogService
from ...services.email_dispatch_service import EmailDispatchService
from ...services.team_service import TeamService
from ..common.ui_helpers import get_current_kst_time, strip_tz


def render_monthly_worklog_dispatch_view():
    """
    📑 [팀 전월 엑셀 원장 정기 발송] 메인 뷰 (Cisco ACI 테마 표준 100% 준수)
    - 매달 1일 08:00에 기술1팀 인원 전체에 대한 전월 카톡/아웃룩 엑셀 원장을 팀메일로 정기 전달
    - 기본 팀메일: GE101@sangsanginworld.co.kr (수정 및 저장 가능)
    - 즉시 테스트 발송 및 엑셀 원장(.xlsx) 브라우저 다운로드 제공
    - 실시간 팀원별 집계 및 원장 데이터 미리보기
    """
    st.markdown("""
    <style>
    /* 🏛️ Cisco ACI 표준 테마: 월간 엑셀 원장 발송 화면 전용 스타일 */
    .monthly-hero {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(2, 44, 67, 0.95) 100%);
        border: 1.5px solid rgba(56, 189, 248, 0.35);
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 22px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    }
    .monthly-hero-title {
        font-size: 21px !important;
        font-weight: 800 !important;
        color: #38bdf8 !important;
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 6px;
    }
    .monthly-hero-desc {
        font-size: 13px !important;
        color: #cbd5e1 !important;
        line-height: 1.6;
    }
    .metric-card-box {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px;
        padding: 14px 16px;
        text-align: center;
    }
    .metric-card-title {
        font-size: 11.5px;
        font-weight: 700;
        color: #94a3b8;
    }
    .metric-card-value {
        font-size: 23px;
        font-weight: 900;
        color: #ffffff;
        margin-top: 4px;
    }
    /* 다운로드 버튼 텍스트 선명한 화이트 보장 */
    div.stDownloadButton > button {
        background-color: #0284c7 !important;
        border: 1px solid #38bdf8 !important;
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
        st.markdown("#### ⚙️ 팀별 정기 발송 설정")
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
        st.markdown("#### 🚀 즉시 테스트 발송 & 원장 다운로드")
        
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

        # 요약 미니 카드
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.markdown(f"""
            <div class="metric-card-box">
                <div class="metric-card-title">총 업무/일정</div>
                <div class="metric-card-value" style="color: #38bdf8;">{tot_rows:,}<span style="font-size: 13px;">건</span></div>
            </div>
            """, unsafe_allow_html=True)
        with mc2:
            st.markdown(f"""
            <div class="metric-card-box">
                <div class="metric-card-title">총 투입 공수</div>
                <div class="metric-card-value" style="color: #4ade80;">{tot_hours:,.1f}<span style="font-size: 13px;">h</span></div>
            </div>
            """, unsafe_allow_html=True)
        with mc3:
            st.markdown(f"""
            <div class="metric-card-box">
                <div class="metric-card-title">카톡 / 아웃룩</div>
                <div class="metric-card-value" style="font-size: 16px; margin-top: 8px; color: #f1f5f9;">{kakao_cnt} / {outlook_cnt}</div>
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

    st.markdown("<hr style='border: 0; border-top: 1px solid rgba(255,255,255,0.08); margin: 28px 0 20px 0;'>", unsafe_allow_html=True)

    # 3. 실시간 데이터 미리보기 (탭 구성)
    st.markdown(f"#### 📊 [{selected_team}] {target_month} 원장 데이터 실시간 미리보기")
    
    if team_df.empty:
        st.info(f"선택하신 [{selected_team}]의 {target_month} 데이터가 없습니다.")
    else:
        tab1, tab2, tab3 = st.tabs([
            "👥 팀원별 투입 현황 요약",
            "💬 카카오톡 업무 원장",
            "📅 아웃룩 캘린더 원장"
        ])

        with tab1:
            worker_group = team_df.groupby("worker_name")
            w_list = []
            for w_name, w_sub in worker_group:
                w_title = w_sub["worker_title"].dropna().iloc[0] if "worker_title" in w_sub.columns and not w_sub["worker_title"].dropna().empty else ""
                k_sub = w_sub[~w_sub["is_outlook"]] if "is_outlook" in w_sub.columns else w_sub
                o_sub = w_sub[w_sub["is_outlook"]] if "is_outlook" in w_sub.columns else pd.DataFrame()
                k_h = round(k_sub["actual_hours"].sum(), 1) if "actual_hours" in k_sub.columns else 0.0
                o_h = round(o_sub["actual_hours"].sum(), 1) if not o_sub.empty and "actual_hours" in o_sub.columns else 0.0
                tot_h = round(w_sub["actual_hours"].sum(), 1) if "actual_hours" in w_sub.columns else 0.0
                ngt_h = round(w_sub[w_sub.get("is_night_work") == True]["actual_hours"].sum(), 1) if "actual_hours" in w_sub.columns and "is_night_work" in w_sub.columns else 0.0
                wkd_h = round(w_sub[w_sub.get("is_weekend_work") == True]["actual_hours"].sum(), 1) if "actual_hours" in w_sub.columns and "is_weekend_work" in w_sub.columns else 0.0

                w_list.append({
                    "담당자": w_name,
                    "직급": w_title,
                    "카톡 건수": len(k_sub),
                    "카톡 공수(h)": k_h,
                    "아웃룩 건수": len(o_sub),
                    "아웃룩 공수(h)": o_h,
                    "총 건수": len(w_sub),
                    "총 공수(h)": tot_h,
                    "야간(h)": ngt_h,
                    "주말(h)": wkd_h
                })
            
            w_df_summary = pd.DataFrame(w_list).sort_values(by="총 공수(h)", ascending=False)
            st.dataframe(w_df_summary, use_container_width=True, hide_index=True)

        with tab2:
            kakao_df = team_df[~team_df["is_outlook"]].copy() if "is_outlook" in team_df.columns else team_df.copy()
            if kakao_df.empty:
                st.info("카카오톡 업무 지원 기록이 없습니다.")
            else:
                disp_k_cols = ["start_time", "end_time", "status", "log_type", "worker_name", "worker_title", "client_name", "task_description", "actual_hours", "is_night_work", "is_weekend_work"]
                disp_k_cols = [c for c in disp_k_cols if c in kakao_df.columns]
                k_out = strip_tz(kakao_df[disp_k_cols].copy())
                if "status" in k_out.columns:
                    k_out["status"] = k_out["status"].map({"COMPLETED": "완료", "PENDING": "진행"}).fillna(k_out["status"])
                st.dataframe(
                    k_out.rename(columns={
                        "start_time": "시작시각", "end_time": "완료시각", "status": "상태",
                        "log_type": "구분", "worker_name": "담당자", "worker_title": "직급",
                        "client_name": "고객사", "task_description": "작업내용",
                        "actual_hours": "소요(h)", "is_night_work": "야간", "is_weekend_work": "주말"
                    }),
                    use_container_width=True,
                    hide_index=True
                )

        with tab3:
            outlook_df = team_df[team_df["is_outlook"]].copy() if "is_outlook" in team_df.columns else pd.DataFrame()
            if outlook_df.empty:
                st.info("아웃룩 캘린더 일정이 없습니다.")
            else:
                disp_o_cols = ["start_time", "end_time", "status", "log_type", "worker_name", "worker_title", "task_description", "actual_hours"]
                disp_o_cols = [c for c in disp_o_cols if c in outlook_df.columns]
                o_out = strip_tz(outlook_df[disp_o_cols].copy())
                if "status" in o_out.columns:
                    o_out["status"] = o_out["status"].map({"COMPLETED": "완료", "PENDING": "예정"}).fillna(o_out["status"])
                st.dataframe(
                    o_out.rename(columns={
                        "start_time": "시작일시", "end_time": "종료일시", "status": "상태",
                        "log_type": "일정구분", "worker_name": "담당자", "worker_title": "직급",
                        "task_description": "일정 내용", "actual_hours": "인정공수(h)"
                    }),
                    use_container_width=True,
                    hide_index=True
                )

    st.markdown("<hr style='border: 0; border-top: 1px solid rgba(255,255,255,0.08); margin: 28px 0 20px 0;'>", unsafe_allow_html=True)

    # 4. 최근 발송 이력
    st.markdown("#### 📜 최근 발송 이력 (전월 엑셀 원장 발송)")
    recent_logs = EmailDispatchService.get_recent_dispatches(limit=10)
    # 전월 원장 관련 이력 우선 필터링
    monthly_logs = [item for item in recent_logs if "전월 원장" in str(item.get("period_label", "")) or "원장" in str(item.get("subject", ""))]
    if not monthly_logs:
        monthly_logs = recent_logs[:5]

    if not monthly_logs:
        st.info("아직 발송된 이력이 없습니다.")
    else:
        for item in monthly_logs:
            d_type = item.get("dispatch_type", "MANUAL_IMMEDIATE")
            d_badge = '<span style="background:#0284c7; color:#ffffff; padding:2px 7px; border-radius:4px; font-size:10.5px; font-weight:800;">🚀 즉시 발송</span>' if "MANUAL" in d_type else '<span style="background:#16a34a; color:#ffffff; padding:2px 7px; border-radius:4px; font-size:10.5px; font-weight:800;">⏳ 정기 자동</span>'
            status = item.get("status", "SUCCESS")
            status_html = '<span style="color:#4ade80; font-weight:800; font-size:11.5px;">✅ 성공</span>' if status == "SUCCESS" else '<span style="color:#f87171; font-weight:800; font-size:11.5px;">❌ 실패</span>'
            dt_str = str(item.get("created_at", "")).replace("T", " ")
            short_dt = dt_str[:16] if len(dt_str) >= 16 else dt_str
            p_label = item.get("period_label", "")
            rcpts = item.get("recipient_emails") or item.get("recipient_email") or ""

            st.markdown(f"""
            <div style="background: rgba(15, 23, 42, 0.7); border: 1.2px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 11px 15px; margin-bottom: 9px;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 7px; margin-bottom: 7px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        {d_badge}
                        <span style="color: #38bdf8; font-weight: 700; font-size: 12.5px;">{p_label}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="color: #94a3b8; font-size: 11px;">{short_dt}</span>
                        {status_html}
                    </div>
                </div>
                <div style="color: #ffffff; font-size: 12px; font-weight: 600;">
                    <span style="color: #38bdf8;">✉️ 수신 메일:</span> {rcpts}
                </div>
            </div>
            """, unsafe_allow_html=True)
