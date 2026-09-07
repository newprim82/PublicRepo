import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from ...analytics.stats_service import StatsService
from ..common.dialogs import show_week_summary_dialog, show_calendar_day_dialog

@st.fragment
def render_trend_interactive_charts(df: pd.DataFrame, monthly_trend: pd.DataFrame, target_months: list, selected_months: list, month_desc: str):
    """월별/주별/일별 추이 인터랙티브 차트 및 클릭 시 팝업 렌더링 (화면 전체 새로고침 없이 독립 Fragment 동작)"""
    col_t3_1, col_t3_2 = st.columns(2)
    with col_t3_1:
        if not monthly_trend.empty:
            range_label = f"{target_months[0]} ~ {target_months[-1]}" if len(target_months) >= 3 else ""
            fig_monthly = px.line(
                monthly_trend,
                x="month_str",
                y="total_hours",
                markers=True,
                text="total_hours",
                labels={"month_str": "월", "total_hours": "총 지원 시간(h)"},
                title=f"월별 총 지원 시간(h) 변동 추이 (지난 2달 포함 3개월 비교: {range_label})"
            )
            fig_monthly.update_traces(
                line_color="#0284c7",
                line_width=3,
                texttemplate='%{text}h',
                textposition='top center',
                marker=dict(size=9, color="#005073", line=dict(width=2, color="#ffffff"))
            )
            fig_monthly.update_layout(
                height=350,
                margin=dict(l=40, r=40, t=50, b=40),
                xaxis=dict(type='category', title="조회 월")
            )
            st.plotly_chart(fig_monthly, use_container_width=True)
        
    event_weekly = None
    event_daily = None

    with col_t3_2:
        weekly_df = df.groupby("week_label")["actual_hours"].sum().reset_index()
        if not weekly_df.empty:
            week_axis_title = "주차(Week)"
            if selected_months and len(selected_months) == 1:
                try:
                    s_dt = pd.to_datetime(selected_months[0] + "-01")
                    e_dt = s_dt + pd.offsets.MonthEnd(1)
                    week_axis_title = f"주차(Week / {s_dt.month}월 {s_dt.day}일 ~ {e_dt.month}월 {e_dt.day}일)"
                except Exception:
                    week_axis_title = f"주차(Week / {month_desc})"
            elif selected_months:
                try:
                    s_dt = pd.to_datetime(min(selected_months) + "-01")
                    e_dt = pd.to_datetime(max(selected_months) + "-01") + pd.offsets.MonthEnd(1)
                    week_axis_title = f"주차(Week / {s_dt.month}월 {s_dt.day}일 ~ {e_dt.month}월 {e_dt.day}일)"
                except Exception:
                    week_axis_title = f"주차(Week / {month_desc})"

            fig_weekly = px.bar(
                weekly_df,
                x="week_label",
                y="actual_hours",
                text="actual_hours",
                labels={"week_label": week_axis_title, "actual_hours": "총 투입 시간(h)"},
                title="주차(Week)별 총 지원 시간 분포"
            )
            fig_weekly.update_traces(
                texttemplate='%{text}h',
                textposition='outside',
                marker_color='#42A5F5',
                customdata=[[w] for w in weekly_df['week_label']]
            )
            fig_weekly.update_layout(
                height=350,
                margin=dict(l=40, r=40, t=50, b=40),
                xaxis=dict(tickangle=-30, title=week_axis_title)
            )
            event_weekly = st.plotly_chart(
                fig_weekly,
                use_container_width=True,
                on_select="rerun",
                selection_mode=["points"],
                key="chart_trend_weekly_bar"
            )

    st.markdown("##### 📅 일자별 작업 시간 분포")
    daily_df = df.groupby("date_str")["actual_hours"].sum().reset_index()
    daily_df = daily_df.sort_values(by="date_str")
    fig_daily = px.bar(
        daily_df,
        x="date_str",
        y="actual_hours",
        text="actual_hours",
        labels={"date_str": "일자", "actual_hours": "작업 시간(h)"},
        title="일자별 작업 시간 분포"
    )
    fig_daily.update_traces(
        texttemplate='%{text}h',
        textposition='outside',
        marker_color='#60A5FA',
        customdata=[[d] for d in daily_df['date_str']]
    )
    fig_daily.update_layout(
        height=320,
        margin=dict(l=40, r=40, t=50, b=40),
        xaxis=dict(type='category', title="작업 일자")
    )
    event_daily = st.plotly_chart(
        fig_daily,
        use_container_width=True,
        on_select="rerun",
        selection_mode=["points"],
        key="chart_trend_daily_bar"
    )

    # 🖱️ 클릭 이벤트 감지 및 세부 작업 내역 모달 팝업 연동
    curr_wk_pt = event_weekly.selection.points[0] if (event_weekly and hasattr(event_weekly, "selection") and event_weekly.selection.points) else None
    curr_day_pt = event_daily.selection.points[0] if (event_daily and hasattr(event_daily, "selection") and event_daily.selection.points) else None

    last_wk_id = st.session_state.get("last_selected_trend_week")
    last_day_id = st.session_state.get("last_selected_trend_day")

    wk_target = None
    if curr_wk_pt:
        if "customdata" in curr_wk_pt and curr_wk_pt["customdata"]:
            cdata = curr_wk_pt["customdata"]
            wk_target = cdata[0] if isinstance(cdata, (list, tuple)) else cdata
        elif "x" in curr_wk_pt:
            wk_target = curr_wk_pt["x"]

    day_target = None
    if curr_day_pt:
        if "customdata" in curr_day_pt and curr_day_pt["customdata"]:
            cdata = curr_day_pt["customdata"]
            day_target = cdata[0] if isinstance(cdata, (list, tuple)) else cdata
        elif "x" in curr_day_pt:
            day_target = curr_day_pt["x"]

    wk_changed = (wk_target is not None) and (wk_target != last_wk_id)
    day_changed = (day_target is not None) and (day_target != last_day_id)

    dialog_to_open = None
    if day_changed:
        st.session_state["last_selected_trend_day"] = day_target
        st.session_state["last_selected_trend_week"] = None
        dialog_to_open = ("day", day_target)
    elif wk_changed:
        st.session_state["last_selected_trend_week"] = wk_target
        st.session_state["last_selected_trend_day"] = None
        dialog_to_open = ("week", wk_target)
    elif day_target and not wk_target:
        dialog_to_open = ("day", day_target)
    elif wk_target and not day_target:
        dialog_to_open = ("week", wk_target)

    if dialog_to_open:
        dtype, dval = dialog_to_open
        if dtype == "week" and dval:
            target_df = df[df["week_label"] == dval]
            if not target_df.empty:
                show_week_summary_dialog(dval, target_df)
        elif dtype == "day" and dval:
            target_df = df[df["date_str"] == dval]
            if not target_df.empty:
                show_calendar_day_dialog(dval, target_df)


@st.fragment


def render_trend_view(df: pd.DataFrame, df_filtered_base: pd.DataFrame, selected_months: list, available_months: list, month_desc: str):
    """📈 월별 / 주별 / 일별 지원 시간 추이 및 시계열 분석 메인 뷰"""
    st.subheader("📈 월별 / 주별 / 일별 지원 시간 추이 및 시계열 분석")

    # 🌟 월별 총 지원 시간 변동 추이: 선택된 조회 월 기준 지난 2달 포함 (총 최근 3개월 비교)
    ref_month = selected_months[0] if selected_months else (available_months[0] if available_months else "")
    target_months = []
    if ref_month:
        try:
            ref_dt = pd.to_datetime(ref_month + "-01")
            m0 = ref_dt.strftime("%Y-%m")
            m1 = (ref_dt - pd.DateOffset(months=1)).strftime("%Y-%m")
            m2 = (ref_dt - pd.DateOffset(months=2)).strftime("%Y-%m")
            target_months = [m2, m1, m0]
        except Exception:
            target_months = [ref_month]

    if target_months and "df_filtered_base" in locals():
        df_trend_3m = df_filtered_base[df_filtered_base["month_str"].isin(target_months)]
    else:
        df_trend_3m = df.copy()

    monthly_trend = StatsService.get_monthly_trend(df_trend_3m)
    if target_months and not monthly_trend.empty:
        base_months_df = pd.DataFrame({"month_str": target_months})
        monthly_trend = pd.merge(base_months_df, monthly_trend, on="month_str", how="left").fillna({
            "total_hours": 0.0, "total_tasks": 0, "night_tasks": 0, "worker_count": 0
        })
        monthly_trend = monthly_trend.sort_values(by="month_str")

    if not df.empty:
        st.markdown("""<div style="background: linear-gradient(90deg, #f0f9ff 0%, #e0f2fe 100%); border: 1px solid #bae6fd; border-left: 4.5px solid #0284c7; border-radius: 6px; padding: 9px 15px; margin: 4px 0 14px 0; font-size: 13px; color: #0369a1; font-weight: 700; display: flex; align-items: center; gap: 8px;">
    <span>💡</span>
    <span><b>그래프의 막대(주차 / 일자)를 클릭</b>하시면, 해당 기간의 <b>[실제 세부 지원 내역 목록 및 카카오톡 원본 대화 팝업]</b>이 바로 열립니다.</span>
    </div>""", unsafe_allow_html=True)
        render_trend_interactive_charts(df, monthly_trend, target_months, selected_months, month_desc)

