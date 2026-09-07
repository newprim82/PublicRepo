import calendar
from datetime import datetime, date, timedelta
import pandas as pd
import streamlit as st

from src.database.supabase_client import db_manager
try:
    from src.database.supabase_client import fetch_outlook_schedules
except ImportError:
    fetch_outlook_schedules = None
from src.services.team_service import TeamService

# 팀원별 아웃룩 고유 색상 매핑 (캡처 사진과 100% 동일)
OUTLOOK_MEMBER_COLORS = {
    "문영민": {"bg": "#d9f99d", "border": "#84cc16", "text": "#365314", "name": "문영민 수석"},
    "이동우": {"bg": "#ffedd5", "border": "#f97316", "text": "#7c2d12", "name": "이동우 수석"},
    "홍정표": {"bg": "#ccfbf1", "border": "#14b8a6", "text": "#134e4a", "name": "홍정표 과장"},
    "전종필": {"bg": "#fef9c3", "border": "#eab308", "text": "#713f12", "name": "전종필 대리"},
    "김시우": {"bg": "#fce7f3", "border": "#ec4899", "text": "#831843", "name": "김시우 사원"},
    "김형일": {"bg": "#cffafe", "border": "#06b6d4", "text": "#164e63", "name": "김형일 수석"},
    "김경현": {"bg": "#ffe4e6", "border": "#f43f5e", "text": "#881337", "name": "김경현 (내 일정)"},
}

DEFAULT_COLOR = {"bg": "#f1f5f9", "border": "#94a3b8", "text": "#0f172a", "name": "기타"}


def render_outlook_calendar_widget():
    """🏠 대시보드 첫 화면 상단에 배치되는 아웃룩 스타일 미래시 통합 캘린더 위젯"""
    # 1. 아웃룩 전용 CSS 주입
    st.markdown("""
    <style>
    .outlook-cal-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 12px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 8px 14px;
    }
    .outlook-grid {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 6px;
        margin-bottom: 16px;
    }
    .outlook-day-header {
        text-align: center;
        font-size: 12.5px;
        font-weight: 800;
        padding: 6px 0;
        background: #f1f5f9;
        border-radius: 6px;
        border: 1px solid #e2e8f0;
    }
    .outlook-cell {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        min-height: 110px;
        max-height: 160px;
        overflow-y: auto;
        padding: 4px 5px;
        font-size: 11px;
        transition: all 0.2s ease;
    }
    .outlook-cell-today {
        background: #f0f9ff !important;
        border: 2px solid #0284c7 !important;
        box-shadow: 0 0 6px rgba(2, 132, 199, 0.2);
    }
    .outlook-cell-other-month {
        background: #fafafa !important;
        opacity: 0.55;
    }
    .outlook-day-num {
        font-size: 11.5px;
        font-weight: 800;
        color: #334155;
        margin-bottom: 4px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .outlook-today-badge {
        background: #0284c7;
        color: #ffffff;
        border-radius: 4px;
        padding: 0 4px;
        font-size: 9.5px;
        font-weight: 800;
    }
    .outlook-chip {
        display: block;
        border-radius: 4px;
        padding: 2px 5px;
        margin-bottom: 3px;
        font-size: 10.5px;
        line-height: 1.35;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        border-left: 3px solid;
    }
    .outlook-tab-bar {
        display: flex;
        gap: 6px;
        overflow-x: auto;
        padding-bottom: 8px;
        margin-bottom: 10px;
    }
    .outlook-tab-item {
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 11.5px;
        font-weight: 700;
        border: 1px solid;
        cursor: pointer;
        white-space: nowrap;
    }
    </style>
    """, unsafe_allow_html=True)

    # 2. 날짜 상태 관리 (세션 스테이트)
    if "outlook_cal_year" not in st.session_state:
        st.session_state["outlook_cal_year"] = 2026
    if "outlook_cal_month" not in st.session_state:
        st.session_state["outlook_cal_month"] = 9
    if "outlook_cal_filter_worker" not in st.session_state:
        st.session_state["outlook_cal_filter_worker"] = "전체 팀원"

    y = st.session_state["outlook_cal_year"]
    m = st.session_state["outlook_cal_month"]
    selected_worker = st.session_state["outlook_cal_filter_worker"]

    # 3. 데이터 로드 (모듈 핫리로드 및 안전 조회 대응)
    df_schedules = pd.DataFrame()
    try:
        if hasattr(db_manager, "fetch_outlook_schedules"):
            df_schedules = db_manager.fetch_outlook_schedules()
        elif fetch_outlook_schedules is not None:
            df_schedules = fetch_outlook_schedules()
        else:
            import importlib
            import src.database.supabase_client as sc
            importlib.reload(sc)
            df_schedules = sc.db_manager.fetch_outlook_schedules()
    except Exception as e_load:
        st.info("📅 아웃룩 일정을 동기화 중입니다. 잠시 후 새로고침 해주세요.")
        return

    if df_schedules.empty:
        # 아직 수집 전이면 안내
        st.info("📅 아웃룩 일정을 동기화하는 중이거나 등록된 일정이 없습니다. (PC B에서 Outlook 수집기가 10분마다 자동 갱신합니다)")
        return

    # 팀원 필터링
    if selected_worker != "전체 팀원":
        df_view = df_schedules[df_schedules["worker_name"] == selected_worker]
    else:
        df_view = df_schedules

    # 4. 상단 컨트롤 바 (오늘 / 이전달 / 다음달 및 팀원 탭)
    col_nav, col_tabs = st.columns([1.2, 2.8])
    with col_nav:
        c1, c2, c3, c4 = st.columns([1, 0.6, 0.6, 2])
        with c1:
            if st.button("오늘", key="btn_out_today", use_container_width=True):
                st.session_state["outlook_cal_year"] = 2026
                st.session_state["outlook_cal_month"] = 9
                st.rerun()
        with c2:
            if st.button("◀", key="btn_out_prev", use_container_width=True):
                if m == 1:
                    st.session_state["outlook_cal_year"] = y - 1
                    st.session_state["outlook_cal_month"] = 12
                else:
                    st.session_state["outlook_cal_month"] = m - 1
                st.rerun()
        with c3:
            if st.button("▶", key="btn_out_next", use_container_width=True):
                if m == 12:
                    st.session_state["outlook_cal_year"] = y + 1
                    st.session_state["outlook_cal_month"] = 1
                else:
                    st.session_state["outlook_cal_month"] = m + 1
                st.rerun()
        with c4:
            st.markdown(f"<div style='font-size: 16px; font-weight: 800; color: #0f172a; padding-top: 4px;'>📅 {y}년 {m}월</div>", unsafe_allow_html=True)

    with col_tabs:
        # 팀원 선택 라디오 또는 셀렉트박스
        avail_workers = ["전체 팀원"] + [w for w in OUTLOOK_MEMBER_COLORS.keys() if w in df_schedules["worker_name"].values]
        worker_choice = st.pills("팀원 필터:", avail_workers, default=selected_worker, key="pills_out_worker")
        if worker_choice and worker_choice != selected_worker:
            st.session_state["outlook_cal_filter_worker"] = worker_choice
            st.rerun()

    # 5. 달력 그리드 계산
    today_dt = date(2026, 9, 7) # 대시보드 기준일
    first_day_of_month = date(y, m, 1)
    # 일요일 시작 (weekday: 월=0 -> 일=6 이므로, (weekday + 1) % 7)
    start_offset = (first_day_of_month.weekday() + 1) % 7
    grid_start_date = first_day_of_month - timedelta(days=start_offset)

    # 5주 or 6주치 그리드 생성 (총 35 or 42칸)
    num_days = calendar.monthrange(y, m)[1]
    total_cells = 35 if (start_offset + num_days) <= 35 else 42

    # 요일 헤더
    day_names = ["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"]
    header_html = '<div class="outlook-grid" style="margin-bottom: 4px;">'
    for idx, d_name in enumerate(day_names):
        col_c = "#dc2626" if idx == 0 else ("#2563eb" if idx == 6 else "#334155")
        header_html += f'<div class="outlook-day-header" style="color: {col_c};">{d_name}</div>'
    header_html += '</div>'
    st.markdown(header_html, unsafe_allow_html=True)

    # 날짜별 셀 렌더링
    grid_html = '<div class="outlook-grid">'
    cur_date = grid_start_date

    for i in range(total_cells):
        is_cur_month = (cur_date.month == m)
        is_today = (cur_date == today_dt)
        date_str = cur_date.strftime("%Y-%m-%d")

        cell_class = "outlook-cell"
        if not is_cur_month:
            cell_class += " outlook-cell-other-month"
        if is_today:
            cell_class += " outlook-cell-today"

        # 해당 일자 일정 필터링 (start_time <= cur_date <= end_time 범위 매칭)
        day_events = df_view[
            (df_view["start_time"].dt.date <= cur_date) &
            (df_view["end_time"].dt.date >= cur_date)
        ]

        # 날짜 숫자 색상 (일: 빨강, 토: 파랑)
        day_color = "#dc2626" if cur_date.weekday() == 6 else ("#2563eb" if cur_date.weekday() == 5 else "#334155")
        today_badge_html = '<span class="outlook-today-badge">오늘</span>' if is_today else ''

        grid_html += f'<div class="{cell_class}">'
        grid_html += f'<div class="outlook-day-num"><span style="color: {day_color};">{cur_date.day}일</span>{today_badge_html}</div>'

        # 일정 칩들 추가
        for _, ev in day_events.iterrows():
            w_name = ev["worker_name"]
            c_info = OUTLOOK_MEMBER_COLORS.get(w_name, DEFAULT_COLOR)
            subj = ev["subject"]
            allday = ev.get("is_all_day", False)
            is_leave = ev.get("is_leave", False)

            if allday or is_leave:
                time_tag = "[종일]" if allday else "[휴가]"
            else:
                st_time_str = ev["start_time"].strftime("%H:%M") if hasattr(ev["start_time"], "strftime") else ""
                time_tag = st_time_str

            leave_icon = "🏖️ " if is_leave else ""
            chip_style = f"background: {c_info['bg']}; border-color: {c_info['border']}; color: {c_info['text']};"
            chip_text = f"{leave_icon}{time_tag} {subj}"

            grid_html += f'<div class="outlook-chip" style="{chip_style}" title="{subj} ({ev.get('duration_hours', 1)}h)">{chip_text}</div>'

        grid_html += '</div>'
        cur_date += timedelta(days=1)

    grid_html += '</div>'
    st.markdown(grid_html, unsafe_allow_html=True)
