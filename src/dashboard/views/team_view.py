import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from ..common.dialogs import show_team_work_logs_dialog
from ..common.ui_helpers import is_same_team

def render_team_comparison_interactive(team_summary: pd.DataFrame, team_df: pd.DataFrame):
    """팀별 업무량 비교 차트 및 상세 표 (화면 전체 새로고침 없는 독립 Fragment)"""
    col_t2_1, col_t2_2 = st.columns(2)
    with col_t2_1:
        fig_team_bar = px.bar(
            team_summary,
            x="worker_team",
            y="total_hours",
            color="worker_team",
            text="total_hours",
            custom_data=["worker_team"],
            labels={"worker_team": "팀", "total_hours": "총 지원 시간(h)"},
            title="팀별 총 지원 시간(h) 비교"
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
            text="avg_hours_per_person",
            custom_data=["worker_team"],
            labels={"worker_team": "팀", "avg_hours_per_person": "1인당 평균 시간(h)"},
            title="팀별 1인당 평균 지원 시간(h) 비교"
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

    st.markdown("##### 📋 팀별 상세 집계 표")
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




def render_team_view(df_raw: pd.DataFrame, selected_months: list):
    """🏢 팀별 총 투입 시간 및 공수 비교 메인 뷰"""
    st.subheader("🏢 팀별 총 투입 시간 및 공수 비교")
    team_df = df_raw.copy()
    if selected_months:
        team_df = team_df[team_df["month_str"].isin(selected_months)]
    
    team_summary = team_df.groupby("worker_team").agg(
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

    render_team_comparison_interactive(team_summary, team_df)

