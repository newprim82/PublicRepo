import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from ..common.dialogs import show_team_work_logs_dialog
from ..common.ui_helpers import (
    is_same_team,
    get_available_weeks_for_df,
    render_empty_week_notice
)

def get_team_fixed_color(team_name: str) -> str:
    """팀별 고유 고정 컬러 매핑 (순위 변동과 무관하게 항상 팀별 고유 색상 유지)"""
    t = str(team_name).replace(" ", "").strip()
    if "본부" in t:
        return "#3b82f6"  # 🏛️ 기술본부: 로열 블루
    elif "1팀" in t:
        return "#06b6d4"  # 🌐 기술 1팀: 스카이 시안 블루
    elif "2팀" in t:
        return "#10b981"  # 🌿 기술 2팀: 에메랄드 그린
    elif "3팀" in t:
        return "#8b5cf6"  # 🍇 기술 3팀: 바이올렛 퍼플
    elif "PI" in t.upper() or "파이" in t:
        return "#f59e0b"  # ⚡ PI팀: 골드 앰버 (주황)
    else:
        return "#64748b"  # 🏢 기타/미배정: 슬레이트 그레이

def render_team_comparison_interactive(team_summary: pd.DataFrame, team_df: pd.DataFrame, current_period_label: str = ""):
    """팀별 업무량 비교 차트 및 상세 표 (화면 전체 새로고침 없는 독립 Fragment)"""
    label_suffix = f" ({current_period_label})" if current_period_label else ""

    # 팀별 고유 고정 색상 딕셔너리 생성
    team_color_map = {
        str(t): get_team_fixed_color(t) for t in team_summary["worker_team"].dropna().unique()
    }

    # 팀별 고유 색상 식별 가이드 칩
    st.markdown("""
    <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; font-size: 12px; font-weight: 800;">
        <span style="background: rgba(59, 130, 246, 0.12); color: #2563eb; border: 1.5px solid #3b82f6; border-radius: 6px; padding: 2px 9px;">🏛️ 기술본부</span>
        <span style="background: rgba(6, 182, 212, 0.12); color: #0891b2; border: 1.5px solid #06b6d4; border-radius: 6px; padding: 2px 9px;">🌐 기술 1팀</span>
        <span style="background: rgba(16, 185, 129, 0.12); color: #059669; border: 1.5px solid #10b981; border-radius: 6px; padding: 2px 9px;">🌿 기술 2팀</span>
        <span style="background: rgba(139, 92, 246, 0.12); color: #7c3aed; border: 1.5px solid #8b5cf6; border-radius: 6px; padding: 2px 9px;">🍇 기술 3팀</span>
        <span style="background: rgba(245, 158, 11, 0.12); color: #d97706; border: 1.5px solid #f59e0b; border-radius: 6px; padding: 2px 9px;">⚡ PI팀</span>
    </div>
    """, unsafe_allow_html=True)

    col_t2_1, col_t2_2 = st.columns(2)
    with col_t2_1:
        fig_team_bar = px.bar(
            team_summary,
            x="worker_team",
            y="total_hours",
            color="worker_team",
            color_discrete_map=team_color_map,
            text="total_hours",
            custom_data=["worker_team"],
            labels={"worker_team": "팀", "total_hours": "총 지원 시간(h)"},
            title=f"팀별 총 지원 시간(h) 비교{label_suffix}"
        )
        fig_team_bar.update_traces(
            texttemplate='%{text}h',
            textposition='outside'
        )
        fig_team_bar.update_layout(height=400, showlegend=False, xaxis=dict(type='category'))
        event_team_bar = st.plotly_chart(
            fig_team_bar,
            use_container_width=True,
            on_select="rerun",
            selection_mode=["points"],
            key="chart_team_total_hours_bar"
        )

    with col_t2_2:
        fig_team_avg = px.bar(
            team_summary,
            x="worker_team",
            y="avg_hours_per_person",
            color="worker_team",
            color_discrete_map=team_color_map,
            text="avg_hours_per_person",
            custom_data=["worker_team"],
            labels={"worker_team": "팀", "avg_hours_per_person": "1인당 평균 시간(h)"},
            title=f"팀별 1인당 평균 지원 시간(h) 비교{label_suffix}"
        )
        fig_team_avg.update_traces(
            texttemplate='%{text}h',
            textposition='outside'
        )
        fig_team_avg.update_layout(height=400, showlegend=False, xaxis=dict(type='category'))
        event_team_avg = st.plotly_chart(
            fig_team_avg,
            use_container_width=True,
            on_select="rerun",
            selection_mode=["points"],
            key="chart_team_avg_hours_bar"
        )

    st.markdown(f"##### 📋 팀별 상세 집계 표{label_suffix}")
    st.caption("💡 표에서 특정 팀 행을 클릭하셔도 해당 팀의 세부 작업 원장 팝업이 바로 열립니다.")
    disp_team_summary = team_summary.rename(columns={
        "worker_team": "소속팀",
        "total_hours": "총 투입시간(h)",
        "total_tasks": "작업 건수",
        "night_tasks": "야간 작업 건수",
        "worker_count": "투입 인원(명)",
        "avg_hours_per_person": "1인당 평균시간(h)"
    })
    event_team_tbl = st.dataframe(
        disp_team_summary,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="tbl_team_summary_selection"
    )

    # 🖱️ 팀 클릭 이벤트 감지 및 세부 작업 원장 모달 팝업 연동
    curr_bar_pt = event_team_bar.selection.points[0] if (event_team_bar and hasattr(event_team_bar, "selection") and event_team_bar.selection.points) else None
    curr_avg_pt = event_team_avg.selection.points[0] if (event_team_avg and hasattr(event_team_avg, "selection") and event_team_avg.selection.points) else None
    curr_tbl_row = event_team_tbl.selection.rows[0] if (event_team_tbl and hasattr(event_team_tbl, "selection") and event_team_tbl.selection.rows) else None

    last_bar_id = st.session_state.get("last_selected_team_bar")
    last_avg_id = st.session_state.get("last_selected_team_avg")
    last_tbl_id = st.session_state.get("last_selected_team_tbl")

    if curr_bar_pt is None and last_bar_id is not None:
        st.session_state["last_selected_team_bar"] = None
        last_bar_id = None
    if curr_avg_pt is None and last_avg_id is not None:
        st.session_state["last_selected_team_avg"] = None
        last_avg_id = None
    if curr_tbl_row is None and last_tbl_id is not None:
        st.session_state["last_selected_team_tbl"] = None
        last_tbl_id = None

    def _extract_pt_team(pt):
        if not pt:
            return None
        if "x" in pt and pt["x"] and str(pt["x"]).strip() and str(pt["x"]) != "None":
            return str(pt["x"]).strip()
        if "customdata" in pt and pt["customdata"]:
            cdata = pt["customdata"]
            val = cdata[0] if isinstance(cdata, (list, tuple)) else cdata
            if val and str(val).strip() and str(val) != "None":
                return str(val).strip()
        if "legendgroup" in pt and pt["legendgroup"]:
            return str(pt["legendgroup"]).strip()
        return None

    bar_target = _extract_pt_team(curr_bar_pt)
    avg_target = _extract_pt_team(curr_avg_pt)

    tbl_target = None
    if curr_tbl_row is not None and curr_tbl_row < len(team_summary):
        tbl_target = str(team_summary.iloc[curr_tbl_row]["worker_team"]).strip()

    bar_changed = (bar_target is not None) and (bar_target != last_bar_id)
    avg_changed = (avg_target is not None) and (avg_target != last_avg_id)
    tbl_changed = (tbl_target is not None) and (tbl_target != last_tbl_id)

    team_to_open = None
    if bar_changed:
        st.session_state["last_selected_team_bar"] = bar_target
        st.session_state["last_selected_team_avg"] = None
        st.session_state["last_selected_team_tbl"] = None
        team_to_open = bar_target
    elif avg_changed:
        st.session_state["last_selected_team_avg"] = avg_target
        st.session_state["last_selected_team_bar"] = None
        st.session_state["last_selected_team_tbl"] = None
        team_to_open = avg_target
    elif tbl_changed:
        st.session_state["last_selected_team_tbl"] = tbl_target
        st.session_state["last_selected_team_bar"] = None
        st.session_state["last_selected_team_avg"] = None
        team_to_open = tbl_target
    elif bar_target and (last_avg_id is None and last_tbl_id is None):
        team_to_open = bar_target
    elif avg_target and (last_bar_id is None and last_tbl_id is None):
        team_to_open = avg_target
    elif tbl_target and (last_bar_id is None and last_avg_id is None):
        team_to_open = tbl_target

    if team_to_open and str(team_to_open).strip() and str(team_to_open).strip() != "None":
        team_target_df = team_df[team_df["worker_team"] == team_to_open]
        if not team_target_df.empty:
            show_team_work_logs_dialog(team_to_open, team_target_df)




def render_team_view(df_raw: pd.DataFrame, selected_months: list, month_desc: str = "", team_mappings: dict = None):
    """🏢 팀별 총 투입 시간 및 공수 비교 메인 뷰"""
    if df_raw.empty:
        st.info("표시할 작업 내역 데이터가 없습니다.")
        return

    team_df = df_raw.copy()
    if selected_months:
        team_df = team_df[team_df["month_str"].isin(selected_months)]

    if team_mappings is None:
        try:
            from ...services.team_service import TeamService
            team_mappings = TeamService.get_team_mappings()
        except Exception:
            team_mappings = {}

    if team_mappings and not team_df.empty:
        from ...services.team_service import UNASSIGNED_TEAM
        team_df["worker_team"] = team_df["worker_name"].map(team_mappings).fillna(team_df.get("worker_team", "")).fillna(UNASSIGNED_TEAM)

    if not month_desc and selected_months:
        month_desc = ", ".join(selected_months)

    # 1. 캘린더 기준 이미 시작된 주차 목록 추출
    available_weeks = get_available_weeks_for_df(team_df, month_desc)
    period_options = ["📅 월간 전체 종합"] + [f"📌 {w}" for w in available_weeks]

    # 2. 토스/Cisco ACI 딥네이비 스타일 라디오 버튼 UI
    st.markdown("""
    <style>
        div.st-key-team_view_period_selector div[role="radiogroup"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: wrap !important;
            gap: 10px !important;
            padding: 8px 12px !important;
            background: #f8fafc !important;
            border: 1.5px solid #005073 !important;
            border-radius: 8px !important;
            margin-bottom: 16px !important;
        }
        div.st-key-team_view_period_selector div[role="radiogroup"] label {
            background: #ffffff !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 6px !important;
            padding: 6px 14px !important;
            margin: 0 !important;
            cursor: pointer !important;
            transition: all 0.15s ease-in-out !important;
        }
        div.st-key-team_view_period_selector div[role="radiogroup"] label:hover {
            background: #e2e8f0 !important;
            border-color: #0284c7 !important;
        }
        div.st-key-team_view_period_selector div[role="radiogroup"] label p,
        div.st-key-team_view_period_selector div[role="radiogroup"] label span {
            color: #002d42 !important;
            font-size: 13px !important;
            font-weight: 800 !important;
        }
        div.st-key-team_view_period_selector div[role="radiogroup"] label[data-checked="true"],
        div.st-key-team_view_period_selector div[role="radiogroup"] label:has(input:checked) {
            background: #005073 !important;
            border-color: #002d42 !important;
        }
        div.st-key-team_view_period_selector div[role="radiogroup"] label[data-checked="true"] p,
        div.st-key-team_view_period_selector div[role="radiogroup"] label:has(input:checked) p,
        div.st-key-team_view_period_selector div[role="radiogroup"] label[data-checked="true"] span,
        div.st-key-team_view_period_selector div[role="radiogroup"] label:has(input:checked) span {
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
            key="team_view_period_selector",
            label_visibility="collapsed"
        )
    else:
        sel_period = "📅 월간 전체 종합"

    # 3. 선택된 주기에 따른 active_df 필터링
    if sel_period != "📅 월간 전체 종합":
        target_week = sel_period.replace("📌 ", "").strip()
        current_period_label = target_week
        if "week_label" in df_raw.columns:
            active_df = df_raw[df_raw["week_label"] == target_week].copy()
        else:
            active_df = team_df[team_df["week_label"] == target_week].copy()

        if team_mappings and not active_df.empty:
            from ...services.team_service import UNASSIGNED_TEAM
            active_df["worker_team"] = active_df["worker_name"].map(team_mappings).fillna(active_df.get("worker_team", "")).fillna(UNASSIGNED_TEAM)
    else:
        current_period_label = month_desc if month_desc else "월간 전체"
        active_df = team_df.copy()

    st.subheader(f"🏢 팀별 총 투입 시간 및 공수 비교 ({current_period_label})")

    if active_df.empty:
        if sel_period != "📅 월간 전체 종합":
            render_empty_week_notice(target_week, "전체 팀")
        else:
            st.info(f"💡 선택하신 기간({current_period_label})에 카카오톡 원장 기록이 없습니다.")
        return

    team_summary = active_df.groupby("worker_team").agg(
        total_hours=("actual_hours", "sum"),
        total_tasks=("id", "count"),
        night_tasks=("is_night_work", "sum"),
        worker_count=("worker_name", "nunique")
    ).reset_index()

    team_summary["total_hours"] = team_summary["total_hours"].round(1)
    team_summary["avg_hours_per_person"] = (team_summary["total_hours"] / team_summary["worker_count"]).round(1)
    team_summary = team_summary.sort_values(by="total_hours", ascending=False).reset_index(drop=True)

    st.markdown("""<div style="background: linear-gradient(90deg, #f0f9ff 0%, #e0f2fe 100%); border: 1px solid #bae6fd; border-left: 4.5px solid #0284c7; border-radius: 6px; padding: 9px 15px; margin: 4px 0 14px 0; font-size: 13px; color: #0369a1; font-weight: 700; display: flex; align-items: center; gap: 8px;">
    <span>💡</span>
    <span><b>각 팀 막대(또는 아래 집계표의 행)를 클릭</b>하시면, 해당 팀의 <b>[실제 세부 지원 내역 원장 및 카카오톡 대화 원본 팝업]</b>이 바로 열립니다.</span>
    </div>""", unsafe_allow_html=True)

    render_team_comparison_interactive(team_summary, active_df, current_period_label)

