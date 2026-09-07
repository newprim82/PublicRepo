import json
import re
import calendar
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from ...services.team_service import TeamService, UNASSIGNED_TEAM
from ..common.dialogs import show_calendar_day_dialog
from ..common.ui_helpers import is_same_team

def render_calendar_and_heatmap_tab(df: pd.DataFrame, df_raw: pd.DataFrame, selected_team: str = "전체 팀"):
    """[📅 작업 캘린더 & 밀도 히트맵] 탭 렌더링 컴포넌트"""
    if df.empty or "start_time" not in df.columns:
        st.info("표시할 작업 데이터가 없습니다.")
        return

    # 🎨 캘린더 탭 전용 선명한 UI 스타일링 주입 (버튼 및 셀렉트박스 고대비 강제)
    st.markdown("""
    <style>
        /* 캘린더 날짜별 상세 버튼 (Cisco ACI Deep Blue + 볼드 화이트 텍스트 상시 노출) */
        div.element-container:has(.cal-day-box) + div.element-container button,
        div.element-container:has(.cal-day-box) + div.element-container .stButton > button,
        div.element-container:has(.cal-day-box) + div.element-container button[kind="primary"],
        div.element-container:has(.cal-day-box) + div.element-container button[kind="secondary"] {
            background-color: #005073 !important;
            color: #ffffff !important;
            border: 1px solid #003852 !important;
            border-radius: 0px 0px 8px 8px !important;
            font-weight: 800 !important;
            font-size: 11.5px !important;
            padding: 4px 6px !important;
            margin-top: -1px !important;
            box-shadow: 0 1px 3px rgba(0, 80, 115, 0.2) !important;
        }
        div.element-container:has(.cal-day-box) + div.element-container button *,
        div.element-container:has(.cal-day-box) + div.element-container button p,
        div.element-container:has(.cal-day-box) + div.element-container button span {
            color: #ffffff !important;
            font-weight: 800 !important;
            font-size: 11.5px !important;
        }
        div.element-container:has(.cal-day-box) + div.element-container button:hover {
            background-color: #003852 !important;
            border-color: #002233 !important;
        }
        div.element-container:has(.cal-day-box) + div.element-container button:hover * {
            color: #ffffff !important;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"### 📅 {selected_team} - 작업 밀도 히트맵 & 월간 캘린더")
    st.caption("날짜별 작업량 집중도, 인터랙티브 월간 달력 및 요일/시간대별 피크타임 골든타임 분석을 제공합니다.")

    # 🌟 [요구사항 반영] 사이드바 기간 필터에 구애받지 않고, 전체 DB(df_raw)에서 선택된 팀의 모든 조회 가능 월 추출
    base_cal_df = df_raw.copy()
    def is_same_team(t1, t2):
        return str(t1).replace(" ", "").strip() == str(t2).replace(" ", "").strip()

    if selected_team not in ["전체", "전체 팀"] and "worker_name" in base_cal_df.columns:
        t_mappings = TeamService.get_team_mappings()
        if t_mappings:
            base_cal_df["worker_team"] = base_cal_df["worker_name"].map(t_mappings).fillna(base_cal_df.get("worker_team", "")).fillna(UNASSIGNED_TEAM)
        base_cal_df = base_cal_df[base_cal_df["worker_team"].apply(lambda t: is_same_team(t, selected_team))]

    if base_cal_df.empty or "start_time" not in base_cal_df.columns:
        st.info("조회 가능한 작업 데이터가 없습니다.")
        return

    available_months = sorted(base_cal_df["start_time"].dt.strftime("%Y-%m").dropna().unique(), reverse=True)
    if not available_months:
        st.info("조회 가능한 작업 기간 데이터가 없습니다.")
        return

    # 가로 길이 축소 (1:3.5 비율로 컴팩트하게 배치)
    col_m_sel, _ = st.columns([1.2, 3.8])
    with col_m_sel:
        st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 5px;">📅 조회 기준 월 선택:</div>', unsafe_allow_html=True)
        pick_month = st.selectbox("조회 기준 월 선택:", options=available_months, index=0, key="cal_pick_month", label_visibility="collapsed")

    df_month = base_cal_df[base_cal_df["start_time"].dt.strftime("%Y-%m") == pick_month].copy()
    if df_month.empty:
        st.info(f"{pick_month}에 등록된 작업 데이터가 없습니다.")
        return

    year, month = map(int, pick_month.split("-"))

    # 1. 상단 월간 핵심 요약 카드 (메인 대시보드와 통일된 세련된 화이트 카드)
    tot_h = round(df_month["actual_hours"].sum(), 1)
    tot_cnt = len(df_month)
    tot_w = df_month["worker_name"].nunique()
    active_days = df_month["start_time"].dt.date.nunique()

    summary_cards_html = f"""<div style="display: flex; gap: 14px; margin-bottom: 22px; flex-wrap: wrap;"><div style="flex: 1; min-width: 140px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #005073; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"><div style="font-size: 12.5px; font-weight: 700; color: #64748b; margin-bottom: 4px;">📅 작업 일수</div><div style="font-size: 24px; font-weight: 900; color: #005073; letter-spacing: -0.5px;">{active_days}일 <span style="font-size: 13px; font-weight: 600; color: #94a3b8;">/ 월</span></div></div><div style="flex: 1; min-width: 140px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #0284c7; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"><div style="font-size: 12.5px; font-weight: 700; color: #64748b; margin-bottom: 4px;">⏱️ 총 투입 공수</div><div style="font-size: 24px; font-weight: 900; color: #0284c7; letter-spacing: -0.5px;">{tot_h}시간</div></div><div style="flex: 1; min-width: 140px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #10b981; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"><div style="font-size: 12.5px; font-weight: 700; color: #64748b; margin-bottom: 4px;">📋 총 작업 건수</div><div style="font-size: 24px; font-weight: 900; color: #10b981; letter-spacing: -0.5px;">{tot_cnt}건</div></div><div style="flex: 1; min-width: 140px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #f59e0b; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"><div style="font-size: 12.5px; font-weight: 700; color: #64748b; margin-bottom: 4px;">👥 투입 인원</div><div style="font-size: 24px; font-weight: 900; color: #f59e0b; letter-spacing: -0.5px;">{tot_w}명</div></div></div>"""
    st.markdown(summary_cards_html, unsafe_allow_html=True)

    # ----------------------------------------------------
    # 2. 🗓️ 인터랙티브 월간 캘린더 그리드 (Monthly Calendar)
    # ----------------------------------------------------
    st.markdown(f"#### 🗓️ {pick_month} 월간 작업 캘린더")
    st.caption("달력의 각 날짜 카드를 클릭하면 그날의 상세 작업 목록 팝업이 즉시 열립니다.")

    df_month["day_num"] = df_month["start_time"].dt.day
    day_summary = df_month.groupby("day_num").agg(
        total_hours=("actual_hours", "sum"),
        total_cnt=("id", "count"),
        workers=("worker_name", lambda x: list(x.unique()))
    ).to_dict("index")

    cal_matrix = calendar.Calendar(firstweekday=6).monthdayscalendar(year, month)
    weekdays = ["일 (Sun)", "월 (Mon)", "화 (Tue)", "수 (Wed)", "목 (Thu)", "금 (Fri)", "토 (Sat)"]

    h_cols = st.columns(7)
    for idx, wd in enumerate(weekdays):
        with h_cols[idx]:
            h_color = "#fca5a5" if idx == 0 else ("#7dd3fc" if idx == 6 else "#ffffff")
            st.markdown(f"<div style='text-align:center; font-weight:800; color:{h_color}; background: linear-gradient(135deg, #002233 0%, #004d71 100%); border: 1px solid #005f8a; padding:7px 4px; border-radius:7px; font-size:12.5px; margin-bottom:8px; box-shadow: 0 2px 5px rgba(0,34,51,0.15);'>{wd}</div>", unsafe_allow_html=True)

    for week in cal_matrix:
        w_cols = st.columns(7)
        for idx, day in enumerate(week):
            with w_cols[idx]:
                if day == 0:
                    st.markdown("<div style='height:92px; background:rgba(241, 245, 249, 0.4); border: 1px dashed #e2e8f0; border-radius:8px; margin-bottom:8px;'></div>", unsafe_allow_html=True)
                else:
                    day_data = day_summary.get(day)
                    num_color = "#dc2626" if idx == 0 else ("#0284c7" if idx == 6 else "#0f172a")

                    if day_data:
                        d_hours = round(day_data["total_hours"], 1)
                        d_cnt = day_data["total_cnt"]
                        d_workers = day_data["workers"][:2]
                        w_str = ", ".join(d_workers) + (f" 외 {len(day_data['workers'])-2}명" if len(day_data["workers"]) > 2 else "")

                        cell_html = f"""<div class="cal-day-box" style="background: #ffffff; border: 1.5px solid #10b981; border-bottom: none; border-radius: 8px 8px 0px 0px; padding: 6px 8px; box-shadow: 0 2px 6px rgba(16, 185, 129, 0.12);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px;"><span style="font-weight: 800; font-size: 13.5px; color: {num_color};">{day}</span><span style="background: #d1fae5; color: #065f46; font-size: 10px; font-weight: 800; padding: 1px 5px; border-radius: 4px; border: 1px solid #a7f3d0;">{d_cnt}건 ({d_hours}h)</span></div><div style="font-size: 11px; color: #334155; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">👥 {w_str}</div></div>"""
                        st.markdown(cell_html, unsafe_allow_html=True)
                        
                        # 클릭 시 상세 팝업 오픈 버튼 (type=primary + cal-day-box 연동으로 상시 선명한 화이트 표시)
                        if st.button(f"🔍 {day}일 상세 ({d_cnt}건)", key=f"btn_cal_pop_{year}_{month}_{day}", type="primary", use_container_width=True):
                            day_target_df = df_month[df_month["day_num"] == day]
                            show_calendar_day_dialog(f"{year}년 {month:02d}월 {day:02d}일", day_target_df)
                    else:
                        cell_html = f"""<div style="min-height:92px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px 8px; margin-bottom: 8px;"><div style="font-weight: 700; font-size: 12.5px; color: {num_color}; opacity: 0.7;">{day}</div><div style="font-size: 11px; color: #94a3b8; margin-top: 18px; text-align: center;">-</div></div>"""
                        st.markdown(cell_html, unsafe_allow_html=True)

    st.write("")
    st.divider()

    # ----------------------------------------------------
    # 3. ⏰ 요일별 × 시간대별 피크타임 골든타임 히트맵
    # ----------------------------------------------------
    st.markdown("#### ⏰ 요일별 × 시작 시간대별 작업 집중도 (골든타임 분석)")
    st.caption("기술본부의 현장 지원이 주로 어느 요일, 몇 시에 시작되는지 한눈에 파악합니다.")

    df_peak = base_cal_df.copy()
    weekday_map = {
        "Monday": "1. 월요일", "Tuesday": "2. 화요일", "Wednesday": "3. 수요일",
        "Thursday": "4. 목요일", "Friday": "5. 금요일", "Saturday": "6. 토요일", "Sunday": "7. 일요일"
    }
    df_peak["weekday_kr"] = df_peak["start_time"].dt.day_name().map(weekday_map)
    df_peak["start_hour"] = df_peak["start_time"].dt.hour

    pivot_df = df_peak.pivot_table(
        index="weekday_kr",
        columns="start_hour",
        values="id",
        aggfunc="count",
        fill_value=0
    ).reindex(["1. 월요일", "2. 화요일", "3. 수요일", "4. 목요일", "5. 금요일", "6. 토요일", "7. 일요일"]).fillna(0)

    for h in range(24):
        if h not in pivot_df.columns:
            pivot_df[h] = 0
    pivot_df = pivot_df[sorted(pivot_df.columns)]
    pivot_df.columns = [f"{h:02d}시" for h in pivot_df.columns]

    fig_peak = px.imshow(
        pivot_df,
        labels=dict(x="시작 시간대", y="요일", color="작업 건수"),
        x=pivot_df.columns,
        y=pivot_df.index,
        color_continuous_scale="Blues",
        aspect="auto",
        text_auto=True
    )
    fig_peak.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=20, b=20),
        height=320,
        font=dict(family="Pretendard, -apple-system, sans-serif", size=12, color="#0f172a"),
        xaxis=dict(
            tickfont=dict(color="#0f172a", size=11, family="Pretendard"),
            title=dict(font=dict(color="#002d42", size=13, family="Pretendard", weight="bold"))
        ),
        yaxis=dict(
            tickfont=dict(color="#0f172a", size=11, family="Pretendard"),
            title=dict(font=dict(color="#002d42", size=13, family="Pretendard", weight="bold"))
        ),
        coloraxis_colorbar=dict(
            title=dict(text="작업 건수", font=dict(color="#002d42", size=12, family="Pretendard", weight="bold")),
            tickfont=dict(color="#0f172a", size=11, family="Pretendard")
        )
    )
    st.plotly_chart(fig_peak, use_container_width=True)

@st.fragment


def render_calendar_view(df: pd.DataFrame, df_raw: pd.DataFrame, selected_team: str = "전체 팀"):
    """📅 작업 캘린더 & 밀도 히트맵 메인 뷰"""
    render_calendar_and_heatmap_tab(df, df_raw, selected_team)
