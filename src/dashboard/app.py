import io
import time
import importlib
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import config
import src.parser.kakao_parser as kakao_parser
import src.parser.reply_matcher as reply_matcher
import src.services.team_service as team_service
import src.database.supabase_client as supabase_client
import src.services.reward_leave_service as reward_leave_service
import src.collector.kakao_auto_collector as kakao_auto_collector

importlib.reload(kakao_parser)
importlib.reload(reply_matcher)
importlib.reload(team_service)
importlib.reload(supabase_client)
importlib.reload(reward_leave_service)
importlib.reload(kakao_auto_collector)

from src.services.team_service import TeamService, DEFAULT_TEAMS, UNASSIGNED_TEAM
from src.services.reward_leave_service import RewardLeaveService
from src.database.supabase_client import db_manager
from src.analytics.stats_service import StatsService
from src.collector.kakao_auto_collector import start_background_collector, run_collection_cycle, get_collector_countdown_info, COLLECTOR_STATUS

@st.cache_resource
def init_single_collector_daemon():
    """Streamlit 수명 주기 전체에서 단 1회만 백그라운드 10분 수집 데몬을 실행"""
    start_background_collector()
    return True

# 🚀 대시보드 구동 시 10분 주기 카카오톡 상시 자동 수집 데몬 1회 단독 기동
try:
    init_single_collector_daemon()
except Exception as e:
    print(f"[수집기 기동 알림]: {e}")

# Streamlit 페이지 설정
st.set_page_config(
    page_title="팀 업무량 & 지원 시간 분석 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS
st.markdown("""
<style>
    html {
        scroll-behavior: smooth;
    }
    /* 🚀 타이틀 + 기준시각 & 우측 Deploy/점세개 최적화 */
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 0px !important;
        z-index: 100 !important;
    }
    [data-testid="stSidebarCollapsedControl"] {
        display: block !important;
        position: fixed !important;
        top: 1.2rem !important;
        left: 1.5rem !important;
        color: #90CAF9 !important;
        background: #1C212D !important;
        border-radius: 8px !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        z-index: 102 !important;
    }
    [data-testid="stToolbar"] {
        display: flex !important;
        align-items: center !important;
        position: absolute !important;
        right: 1.5rem !important;
        top: 1.15rem !important;
        height: 32px !important;
        margin: 0px !important;
        padding: 0px !important;
        opacity: 0.9 !important;
        z-index: 101 !important;
    }
    .block-container {
        padding-top: 1.15rem !important;
        padding-bottom: 2rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }
    /* 타이틀 및 헤더 영역 컴팩트 최적화 */
    .dashboard-title-box {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
        padding-top: 2px;
        padding-bottom: 10px;
        padding-right: 120px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .main-title-text {
        font-size: 25px;
        font-weight: 900;
        color: #FFFFFF;
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
    }
    .filter-badge {
        background-color: #1a233a;
        color: #90caf9;
        padding: 10px 16px;
        border-radius: 10px;
        font-size: 14px;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 18px;
        border: 1px solid #283593;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    }
    .menu-header {
        font-size: 16px;
        font-weight: bold;
        color: #1E88E5;
        margin-bottom: 8px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        white-space: pre-wrap;
        background-color: #181B22;
        color: #A0AEC0;
        border-radius: 8px 8px 0px 0px;
        padding-top: 10px;
        padding-bottom: 10px;
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    .stTabs [aria-selected="true"] {
        background-color: #1E88E5 !important;
        color: white !important;
        font-weight: bold;
    }
    /* 🌟 프리미엄 네온 KPI 카드 스타일 */
    .kpi-card {
        background: linear-gradient(145deg, #1C212D, #131722);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 14px;
        padding: 18px 20px;
        margin-bottom: 12px;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.35);
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }
    .kpi-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.5);
    }
    .kpi-title {
        font-size: 13px;
        font-weight: 700;
        color: #94A3B8;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 6px;
        letter-spacing: -0.2px;
    }
    .kpi-value {
        font-size: 32px;
        font-weight: 900;
        line-height: 1.1;
        margin-bottom: 10px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    .kpi-unit {
        font-size: 16px;
        font-weight: 600;
        color: #64748B;
        margin-left: 4px;
    }
    .kpi-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 11.5px;
        font-weight: 700;
        letter-spacing: -0.2px;
    }
    .badge-cyan { background: rgba(0, 229, 255, 0.12); color: #00E5FF; border: 1px solid rgba(0, 229, 255, 0.25); }
    .badge-green { background: rgba(0, 230, 118, 0.12); color: #00E676; border: 1px solid rgba(0, 230, 118, 0.25); }
    .badge-purple { background: rgba(179, 136, 255, 0.12); color: #B388FF; border: 1px solid rgba(179, 136, 255, 0.25); }
    .badge-amber { background: rgba(255, 171, 0, 0.12); color: #FFAB00; border: 1px solid rgba(255, 171, 0, 0.25); }
    .badge-red { background: rgba(255, 82, 82, 0.12); color: #FF5252; border: 1px solid rgba(255, 82, 82, 0.25); }
    
    /* 🎯 사이드바 정돈된 섹션 카드 헤더 */
    .sidebar-section-header {
        font-size: 13.5px;
        font-weight: 800;
        color: #E2E8F0;
        background: rgba(30, 41, 59, 0.7);
        padding: 6px 12px;
        border-radius: 8px;
        border-left: 4px solid #00E5FF;
        margin-top: 10px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 6px;
        letter-spacing: -0.2px;
    }
    .sidebar-section-header.purple { border-left-color: #B388FF; }
    .sidebar-section-header.green { border-left-color: #00E676; }
    .sidebar-section-header.amber { border-left-color: #FFAB00; }
    
    /* ✨ [과중 근무 발생 알림] 흰색/빨간색 교차 반짝임(Blinking) 애니메이션 */
    @keyframes alert-blink {
        0% {
            color: #FFFFFF;
            border-color: #FF1744;
            background-color: rgba(255, 23, 68, 0.4);
            box-shadow: 0 0 14px rgba(255, 23, 68, 0.9), inset 0 0 8px rgba(255, 23, 68, 0.5);
            text-shadow: 0 0 8px #FFFFFF;
        }
        50% {
            color: #FF1744;
            border-color: #FFFFFF;
            background-color: rgba(255, 255, 255, 0.25);
            box-shadow: 0 0 20px rgba(255, 255, 255, 0.95), inset 0 0 10px rgba(255, 255, 255, 0.6);
            text-shadow: 0 0 10px #FF1744;
        }
        100% {
            color: #FFFFFF;
            border-color: #FF1744;
            background-color: rgba(255, 23, 68, 0.4);
            box-shadow: 0 0 14px rgba(255, 23, 68, 0.9), inset 0 0 8px rgba(255, 23, 68, 0.5);
            text-shadow: 0 0 8px #FFFFFF;
        }
    }

    @keyframes siren-pulse {
        0% { transform: scale(1) rotate(0deg); }
        20% { transform: scale(1.25) rotate(-12deg); }
        40% { transform: scale(1.25) rotate(12deg); }
        60% { transform: scale(1.25) rotate(-8deg); }
        80% { transform: scale(1.25) rotate(8deg); }
        100% { transform: scale(1) rotate(0deg); }
    }

    .alert-blink-badge {
        animation: alert-blink 1.2s infinite ease-in-out !important;
        padding: 3px 12px !important;
        border-radius: 8px !important;
        border: 2px solid #FF1744 !important;
        font-weight: 900 !important;
        font-size: 15px !important;
        letter-spacing: -0.3px !important;
        display: inline-block !important;
    }

    .siren-icon {
        display: inline-block !important;
        animation: siren-pulse 1.2s infinite ease-in-out !important;
        font-size: 18px !important;
    }

    /* 🚨 과중 근무 배너 컨테이너 테두리 & 배경 (일체형 네모칸) */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) {
        background: linear-gradient(135deg, rgba(211, 47, 47, 0.22), rgba(239, 108, 0, 0.22)) !important;
        border: 1.5px solid rgba(255, 82, 82, 0.6) !important;
        border-left: 8px solid #FF1744 !important;
        border-radius: 14px !important;
        box-shadow: 0 6px 24px rgba(255, 23, 68, 0.3) !important;
        padding: 14px 20px !important;
        margin-top: 14px !important;
        margin-bottom: 18px !important;
    }

    /* 🟢 과중 근무 없음 (정상 상태) 배너 컨테이너 테두리 & 배경 */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.normal-status-badge) {
        background: linear-gradient(135deg, rgba(0, 230, 118, 0.08), rgba(0, 229, 255, 0.05)) !important;
        border: 1.5px solid rgba(0, 230, 118, 0.35) !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 16px rgba(0, 230, 118, 0.12) !important;
        padding: 12px 20px !important;
        margin-top: 10px !important;
        margin-bottom: 16px !important;
        text-align: center !important;
    }

    .normal-status-badge {
        background: rgba(0, 230, 118, 0.18) !important;
        color: #00E676 !important;
        border: 1.5px solid rgba(0, 230, 118, 0.6) !important;
        padding: 3px 12px !important;
        border-radius: 8px !important;
        font-weight: 900 !important;
        font-size: 13.5px !important;
        letter-spacing: -0.3px !important;
        display: inline-flex !important;
        align-items: center !important;
    }

    /* 🟧 배너 내부 버튼 100% 강제 오렌지색 적용 */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) .stButton button,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) button {
        background: linear-gradient(135deg, #FF6D00, #FF9100) !important;
        background-color: #FF6D00 !important;
        color: #FFFFFF !important;
        border: 1.5px solid #FFE082 !important;
        border-radius: 20px !important;
        padding: 4px 16px !important;
        font-size: 13px !important;
        font-weight: 900 !important;
        min-height: 32px !important;
        height: 32px !important;
        line-height: 22px !important;
        box-shadow: 0 4px 14px rgba(255, 109, 0, 0.6) !important;
        white-space: nowrap !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) .stButton button *,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) button * {
        color: #FFFFFF !important;
        font-weight: 900 !important;
        font-size: 13px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) .stButton button:hover,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) button:hover {
        background: linear-gradient(135deg, #FF9100, #FFAB00) !important;
        transform: translateY(-2px) scale(1.04) !important;
        box-shadow: 0 6px 20px rgba(255, 109, 0, 0.85) !important;
    }
</style>
""", unsafe_allow_html=True)


def load_data() -> pd.DataFrame:
    df = db_manager.fetch_all_work_logs()
    if not df.empty:
        mappings = TeamService.get_team_mappings()
        if mappings:
            df["worker_team"] = df["worker_name"].map(mappings).fillna(df["worker_team"]).fillna(UNASSIGNED_TEAM)
            
        # week_str, week_label 안전 보장
        if "start_time" in df.columns:
            df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
            df["month_str"] = df["start_time"].dt.strftime("%Y-%m")
            df["date_str"] = df["start_time"].dt.strftime("%Y-%m-%d")
            
            def get_week_label(dt):
                if pd.isna(dt):
                    return ""
                from datetime import timedelta
                mon = dt - timedelta(days=dt.weekday())
                sun = mon + timedelta(days=6)
                week_of_month = (mon.day - 1) // 7 + 1
                return f"{mon.strftime('%Y-%m')} {week_of_month}주차 ({mon.strftime('%m/%d')}~{sun.strftime('%m/%d')})"

            df["week_str"] = df["start_time"].dt.strftime("%G-W%V")
            df["week_label"] = df["start_time"].apply(get_week_label)
        else:
            df["week_str"] = ""
            df["week_label"] = ""
    return df


def clear_all_caches_and_db():
    db_manager.clear_all_data()
    st.cache_data.clear()
    st.cache_resource.clear()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    importlib.reload(kakao_parser)
    importlib.reload(reply_matcher)


def format_raw_chat_display(row) -> str:
    """카카오톡 시작보고/완료보고 메시지 앞에 정확한 보고 일시를 첨부하여 포맷팅"""
    st_time = row['start_time'].strftime('%Y-%m-%d %H:%M') if ('start_time' in row and pd.notna(row['start_time'])) else '시각 미상'
    ed_time = row['end_time'].strftime('%Y-%m-%d %H:%M') if ('end_time' in row and pd.notna(row['end_time'])) else ''
    
    raw_start = row.get('raw_start_message', '(시작 원본 없음)')
    raw_end = row.get('raw_end_message', '')
    
    start_line = f"시작 보고 ({st_time}): {raw_start}"
    if raw_end:
        ed_label = f" ({ed_time})" if ed_time else ""
        end_line = f"완료 보고{ed_label}: {raw_end}"
    else:
        end_line = "완료 보고: (완료 메시지 없음 - 예정시간 기준 자동완료)"
    return f"{start_line}\n{end_line}"


# ==========================================
# 팝업 대화상자 (모달 다이얼로그) - 최상단 전역 정의
# ==========================================
@st.dialog("🔍 세부 작업 내역 및 카카오톡 원본 분석", width="large")
def show_weekly_detail_dialog(target_worker: str, df_data: pd.DataFrame, default_week_name: str = None):
    worker_df = df_data[df_data["worker_name"] == target_worker]
    if worker_df.empty:
        st.warning(f"[{target_worker}] 님의 작업 데이터가 없습니다.")
        return

    # 주차 목록 (시간 많은 순 정렬)
    wk_agg = worker_df.groupby("week_label")["actual_hours"].agg(["sum", "count"]).reset_index()
    wk_agg = wk_agg.sort_values(by="sum", ascending=False)

    wk_options = []
    wk_map = {}
    default_pick_idx = 0

    for idx, (_, r) in enumerate(wk_agg.iterrows()):
        lbl = r["week_label"]
        s = round(r["sum"], 1)
        c = int(r["count"])
        alert_icon = " 🚨 (주 52h 초과)" if s >= 52.0 else (" ⚠️ (주 40h 초과)" if s >= 40.0 else "")
        disp = f"{lbl} ➔ 총 {s}시간 ({c}건){alert_icon}"
        wk_options.append(disp)
        wk_map[disp] = lbl

        # 사용자가 클릭한 셀의 주차가 일치하는 경우 기본 인덱스로 자동 선택!
        if default_week_name and (default_week_name in lbl or lbl in default_week_name):
            default_pick_idx = idx

    st.markdown(f"### 👤 **{target_worker}** 님의 주차별 세부 작업 분석")
    
    col_wk_pick, _ = st.columns([2, 1])
    with col_wk_pick:
        selected_wk_disp = st.selectbox(
            "📆 상세 내역을 확인할 주차를 선택하세요:",
            options=wk_options,
            index=default_pick_idx,
            key=f"modal_wk_select_{target_worker}_{default_pick_idx}"
        )
        target_wk = wk_map.get(selected_wk_disp, "")

    if target_wk:
        detail = worker_df[worker_df["week_label"] == target_wk].sort_values(by="start_time", ascending=True)
        tot_h = round(detail["actual_hours"].sum(), 1)
        tot_cnt = len(detail)
        night_tasks = int(detail["is_night_work"].sum())
        weekend_tasks = int(detail["is_weekend_work"].sum()) if "is_weekend_work" in detail.columns else 0
        clients = list(detail["client_name"].unique())

        # 지표 카드 (주 52시간 기준 산정)
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric(
                "해당 주차 총 투입 시간",
                f"{tot_h}시간",
                delta=f"{round(tot_h - 52.0, 1)}h 초과!" if tot_h >= 52.0 else "주 52h 이내 정상",
                delta_color="inverse" if tot_h >= 52.0 else "normal"
            )
        with m2:
            st.metric("총 작업 건수", f"{tot_cnt}건")
        with m3:
            st.metric("야간 / 주말 작업", f"야간 {night_tasks}건 / 주말 {weekend_tasks}건")
        with m4:
            st.metric("지원 고객사 수", f"{len(clients)}개사")

        # ----------------------------------------------------
        # 🎁 초과 근무 보상 휴가 관리 (지표 카드 바로 아래 배치)
        # ----------------------------------------------------
        st.markdown("---")
        st.markdown("#### 🎁 초과 근무 보상 휴가 부여 및 관리")
        
        curr_reward = RewardLeaveService.get_reward_leave(target_worker, target_wk)

        if curr_reward:
            st.success(f"✅ **보상 휴가 부여 완료**: **{curr_reward['leave_hours']}시간 ({curr_reward['note']})**  \n*(최종 등록 시각: {curr_reward['updated_at']})*")
            col_btn_del, _ = st.columns([1, 2])
            with col_btn_del:
                if st.button("🗑️ 보상 휴가 취소/삭제 (미보상 전환)", key=f"del_reward_{target_worker}_{target_wk}", use_container_width=True):
                    RewardLeaveService.delete_reward_leave(target_worker, target_wk)
                    st.toast("보상 휴가 기록이 삭제되었습니다.", icon="🗑️")
                    st.rerun()
        else:
            if tot_h >= 52.0:
                st.warning(f"🚨 **주 52시간 초과 근무 {round(tot_h - 52.0, 1)}시간 발생** (미보상 상태). 아래에서 보상 휴가를 등록하시면 표의 색상이 **초록색**으로 전환됩니다.")
            elif tot_h >= 40.0:
                st.info(f"⚠️ 주 40시간 초과({tot_h}시간) 주차입니다. 필요 시 보상 휴가를 등록하시면 표에 반영됩니다.")
            else:
                st.info("💡 해당 주차는 주 52시간 이내 정상이지만, 필요 시 특별 보상 휴가를 등록할 수 있습니다.")

            with st.form(f"form_reward_leave_{target_worker}_{target_wk}"):
                col_hrs, col_note = st.columns([1, 2])
                with col_hrs:
                    default_leave_hrs = 8.0 if tot_h >= 52.0 else 4.0
                    input_leave_hrs = st.number_input("보상 시간(h):", value=default_leave_hrs, step=0.5, min_value=0.5)
                with col_note:
                    input_leave_note = st.text_input("보상 내용 및 휴가 메모:", value="대체 휴무 1일 부여 완료" if default_leave_hrs >= 8.0 else "반차 부여 완료", help="예: 8/21 대체휴무 1일 부여, 8/25 반차 등")
                
                btn_save_reward = st.form_submit_button("💾 보상 휴가 부여 확정 (초록색 전환)", use_container_width=True)
                if btn_save_reward:
                    RewardLeaveService.save_reward_leave(target_worker, target_wk, input_leave_hrs, input_leave_note)
                    st.toast(f"🎉 [{target_worker}] 님에게 보상 휴가가 성공적으로 부여되었습니다!", icon="✅")
                    st.rerun()

        st.divider()

        # 고객사별 시간 분배 바 차트
        c_grp = detail.groupby("client_name")["actual_hours"].sum().reset_index()
        fig = px.bar(
            c_grp,
            x="client_name",
            y="actual_hours",
            text="actual_hours",
            color="client_name",
            labels={"client_name": "고객사", "actual_hours": "투입시간(h)"},
            title=f"고객사별 투입 시간 분포 (총 {tot_h}h)"
        )
        fig.update_traces(texttemplate='%{text}h', textposition='outside')
        fig.update_layout(height=260, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        # 세부 작업 내역 리스트
        st.markdown("#### 📋 세부 작업 내역 원장")
        st.dataframe(
            detail[[
                "start_time", "client_name", "task_description",
                "actual_hours", "status", "is_night_work"
            ]].rename(columns={
                "start_time": "시작 보고시각",
                "client_name": "고객사",
                "task_description": "작업내용",
                "actual_hours": "소요(h)",
                "status": "상태",
                "is_night_work": "야간여부"
            }),
            use_container_width=True,
            hide_index=True
        )

        # 카카오톡 원본 메시지 아코디언
        with st.expander(f"💬 카카오톡 시작/완료 원본 메시지 전수 보기 ({tot_cnt}건)", expanded=False):
            for i, (_, r) in enumerate(detail.iterrows()):
                st.markdown(f"**[작업 #{i+1}] {r['start_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(r['start_time']) else ''} | {r['client_name']} - {r['task_description']} ({r['actual_hours']}h)**")
                st.code(format_raw_chat_display(r), language="text")
                st.divider()



# ----------------------------------------------------
# 🌟 5대 핵심 KPI 카드별 세부 내역 팝업 모달 (@st.dialog)
# ----------------------------------------------------
@st.dialog("⏱️ 총 지원 시간 세부 작업 내역", width="large")
def show_kpi_total_hours_dialog(df_data: pd.DataFrame):
    if df_data.empty:
        st.info("데이터가 없습니다.")
        return
    tot_h = round(df_data["actual_hours"].sum(), 1)
    avg_h = round(df_data["actual_hours"].mean(), 1) if len(df_data) > 0 else 0.0
    st.markdown(f"### ⏱️ 총 지원 시간: **{tot_h:,}시간**  \n*(총 {len(df_data):,}건 / 건당 평균 소요시간: {avg_h}h)*")
    
    c1, c2 = st.columns([1, 1])
    with c1:
        top_clients = df_data.groupby("client_name")["actual_hours"].sum().sort_values(ascending=False).head(5).reset_index()
        fig = px.bar(top_clients, x="actual_hours", y="client_name", orientation="h", text="actual_hours", title="🏢 상위 5개 고객사 투입 시간(h)")
        fig.update_layout(height=220, yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        top_workers = df_data.groupby("worker_name")["actual_hours"].sum().sort_values(ascending=False).head(5).reset_index()
        fig2 = px.bar(top_workers, x="actual_hours", y="worker_name", orientation="h", text="actual_hours", title="👤 상위 5개 담당자 투입 시간(h)")
        fig2.update_layout(height=220, yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig2, use_container_width=True)

    sorted_df = df_data.sort_values(by="start_time", ascending=False).reset_index(drop=True)
    
    st.markdown("#### 📋 전체 지원 작업 상세 목록")
    st.caption("💡 표에서 특정 행을 클릭하시면, 해당 작업의 **카카오톡 시작/완료 원본 메시지**를 바로 아래에서 확인하실 수 있습니다.")
    sel_tbl = st.dataframe(
        sorted_df[[
            "start_time", "worker_name", "worker_team",
            "client_name", "task_description", "estimated_hours", "actual_hours", "status"
        ]].rename(columns={
            "start_time": "시작 보고시각",
            "worker_name": "담당자",
            "worker_team": "소속팀",
            "client_name": "고객사",
            "task_description": "작업내용",
            "estimated_hours": "예정(h)",
            "actual_hours": "소요(h)",
            "status": "상태"
        }),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    # 행 선택 시 카카오톡 원본 메시지 노출
    if sel_tbl and hasattr(sel_tbl, "selection") and sel_tbl.selection.rows:
        sel_idx = sel_tbl.selection.rows[0]
        sel_row = sorted_df.iloc[sel_idx]
        st.markdown(f"##### 💬 [{sel_row['worker_name']} | {sel_row['client_name']}] 카카오톡 대화 원본")
        st.code(format_raw_chat_display(sel_row), language="text")

    with st.expander(f"💬 전체 작업 카카오톡 원본 메시지 전수 보기 ({len(sorted_df)}건)", expanded=False):
        for i, (_, r) in enumerate(sorted_df.iterrows()):
            st.markdown(f"**[작업 #{i+1}] {r['start_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(r['start_time']) else ''} | {r['worker_name']} - {r['client_name']} ({r['task_description']}) [예정:{r.get('estimated_hours',0)}h ➔ 소요:{r.get('actual_hours',0)}h]**")
            st.code(format_raw_chat_display(r), language="text")
            st.divider()


@st.dialog("📋 총 작업 건수 세부 내역 (완료 / 진행 중)", width="large")
def show_kpi_total_tasks_dialog(df_data: pd.DataFrame):
    if df_data.empty:
        st.info("데이터가 없습니다.")
        return
    comp_df = df_data[df_data["status"] == "COMPLETED"].sort_values(by="start_time", ascending=False).reset_index(drop=True)
    pend_df = df_data[df_data["status"] != "COMPLETED"].sort_values(by="start_time", ascending=False).reset_index(drop=True)
    
    st.markdown(f"### 📋 총 작업 건수: **{len(df_data):,}건** (🟢 완료 {len(comp_df)}건 | 🟡 진행 중 {len(pend_df)}건)")
    
    t_tab1, t_tab2 = st.tabs([f"🟢 완료된 작업 ({len(comp_df)}건)", f"🟡 진행 중인 작업 ({len(pend_df)}건)"])
    with t_tab1:
        st.caption("💡 표에서 행을 클릭하시면 해당 작업의 **카카오톡 시작/완료 원본 메시지**가 아래에 표시됩니다.")
        sel_t1 = st.dataframe(
            comp_df[[
                "start_time", "worker_name", "worker_team",
                "client_name", "task_description", "estimated_hours", "actual_hours"
            ]].rename(columns={
                "start_time": "시작 보고시각",
                "worker_name": "담당자",
                "worker_team": "소속팀",
                "client_name": "고객사",
                "task_description": "작업내용",
                "estimated_hours": "예정(h)",
                "actual_hours": "소요(h)"
            }),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="comp_tasks_table"
        )
        if sel_t1 and hasattr(sel_t1, "selection") and sel_t1.selection.rows:
            sel_r1 = comp_df.iloc[sel_t1.selection.rows[0]]
            st.markdown(f"##### 💬 [{sel_r1['worker_name']} | {sel_r1['client_name']}] 카카오톡 대화 원본")
            st.code(format_raw_chat_display(sel_r1), language="text")

    with t_tab2:
        if pend_df.empty:
            st.success("🎉 현재 진행 중(미완료)인 잔여 작업이 없습니다!")
        else:
            st.caption("💡 표에서 행을 클릭하시면 시작 보고 원본 메시지가 표시됩니다.")
            sel_t2 = st.dataframe(
                pend_df[[
                    "start_time", "worker_name", "worker_team",
                    "client_name", "task_description", "estimated_hours"
                ]].rename(columns={
                    "start_time": "시작시각",
                    "worker_name": "담당자",
                    "worker_team": "소속팀",
                    "client_name": "고객사",
                    "task_description": "작업내용",
                    "estimated_hours": "예정(h)"
                }),
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="pend_tasks_table"
            )
            if sel_t2 and hasattr(sel_t2, "selection") and sel_t2.selection.rows:
                sel_r2 = pend_df.iloc[sel_t2.selection.rows[0]]
                st.markdown(f"##### 💬 [{sel_r2['worker_name']} | {sel_r2['client_name']}] 카카오톡 시작 보고 원본")
                st_time = sel_r2['start_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(sel_r2['start_time']) else '시각 미상'
                st.code(f"시작 보고 ({st_time}): {sel_r2.get('raw_start_message', '')}", language="text")


@st.dialog("👥 투입 인원 및 팀원별 공수 상세", width="large")
def show_kpi_workers_dialog(df_data: pd.DataFrame):
    if df_data.empty:
        st.info("데이터가 없습니다.")
        return
    w_summary = StatsService.get_worker_summary(df_data)
    st.markdown(f"### 👥 총 투입 인원: **{len(w_summary)}명** (1인당 평균 {round(df_data['actual_hours'].sum() / max(len(w_summary), 1), 1)}h)")
    
    st.dataframe(
        w_summary.rename(columns={
            "worker_name": "담당자",
            "team": "소속팀",
            "total_hours": "총 투입시간(h)",
            "task_count": "작업 건수",
            "night_tasks": "야간 건수",
            "weekend_tasks": "주말 건수",
            "avg_hours": "건당 평균(h)"
        }),
        use_container_width=True,
        hide_index=True
    )


@st.dialog("🌙 야간 / 주말 긴급 작업 세부 내역", width="large")
def show_kpi_urgent_dialog(df_data: pd.DataFrame):
    if df_data.empty:
        st.info("데이터가 없습니다.")
        return
    night_df = df_data[df_data["is_night_work"] == True].sort_values(by="start_time", ascending=False).reset_index(drop=True) if "is_night_work" in df_data.columns else pd.DataFrame()
    weekend_df = df_data[df_data["is_weekend_work"] == True].sort_values(by="start_time", ascending=False).reset_index(drop=True) if "is_weekend_work" in df_data.columns else pd.DataFrame()
    
    st.markdown(f"### 🌙 긴급 작업: 총 **{len(night_df) + len(weekend_df)}건** (🌙 야간 {len(night_df)}건 | 🏖️ 주말 {len(weekend_df)}건)")
    
    u_tab1, u_tab2 = st.tabs([f"🌙 야간 작업 목록 ({len(night_df)}건)", f"🏖️ 주말 작업 목록 ({len(weekend_df)}건)"])
    with u_tab1:
        if night_df.empty:
            st.info("야간 작업 내역이 없습니다.")
        else:
            st.caption("💡 표에서 행을 클릭하시면 **카카오톡 시작/완료 보고 원본 대화**가 아래에 표시됩니다.")
            sel_u1 = st.dataframe(
                night_df[[
                    "start_time", "worker_name", "worker_team",
                    "client_name", "task_description", "actual_hours"
                ]].rename(columns={
                    "start_time": "시작 보고시각",
                    "worker_name": "담당자",
                    "worker_team": "소속팀",
                    "client_name": "고객사",
                    "task_description": "작업내용",
                    "actual_hours": "소요(h)"
                }),
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="night_tasks_table"
            )
            if sel_u1 and hasattr(sel_u1, "selection") and sel_u1.selection.rows:
                sel_un = night_df.iloc[sel_u1.selection.rows[0]]
                st.markdown(f"##### 💬 [{sel_un['worker_name']} | {sel_un['client_name']}] 야간 작업 카카오톡 원본")
                st.code(format_raw_chat_display(sel_un), language="text")

    with u_tab2:
        if weekend_df.empty:
            st.info("주말 작업 내역이 없습니다.")
        else:
            st.caption("💡 표에서 행을 클릭하시면 **카카오톡 시작/완료 보고 원본 대화**가 아래에 표시됩니다.")
            sel_u2 = st.dataframe(
                weekend_df[[
                    "start_time", "worker_name", "worker_team",
                    "client_name", "task_description", "actual_hours"
                ]].rename(columns={
                    "start_time": "시작 보고시각",
                    "worker_name": "담당자",
                    "worker_team": "소속팀",
                    "client_name": "고객사",
                    "task_description": "작업내용",
                    "actual_hours": "소요(h)"
                }),
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="weekend_tasks_table"
            )
            if sel_u2 and hasattr(sel_u2, "selection") and sel_u2.selection.rows:
                sel_uw = weekend_df.iloc[sel_u2.selection.rows[0]]
                st.markdown(f"##### 💬 [{sel_uw['worker_name']} | {sel_uw['client_name']}] 주말 작업 카카오톡 원본")
                st.code(format_raw_chat_display(sel_uw), language="text")


@st.dialog("⚠️ 예정 시간 초과 작업 세부 내역 및 카카오톡 원본 확인", width="large")
def show_kpi_overdue_dialog(df_data: pd.DataFrame):
    if df_data.empty:
        st.info("데이터가 없습니다.")
        return
    overdue_df = df_data[df_data["actual_hours"] > df_data["estimated_hours"]].copy()
    if not overdue_df.empty:
        overdue_df["diff_hours"] = (overdue_df["actual_hours"] - overdue_df["estimated_hours"]).round(1)
        overdue_df = overdue_df.sort_values(by="diff_hours", ascending=False).reset_index(drop=True)
        
    st.markdown(f"### ⚠️ 예정 시간 초과 작업: 총 **{len(overdue_df)}건** (초과율 {round(len(overdue_df)/max(len(df_data), 1)*100, 1)}%)")
    
    if overdue_df.empty:
        st.success("🎉 예정 시간을 초과한 작업이 전혀 없습니다!")
    else:
        st.caption("💡 **표에서 확인하고 싶은 작업 행을 클릭**하시면, 해당 작업의 **카카오톡 시작 보고 & 완료 보고 원본 메시지 전문**과 **지연 괴리 사유**를 바로 아래에서 상세히 확인하실 수 있습니다.")
        
        sel_overdue = st.dataframe(
            overdue_df[[
                "start_time", "worker_name", "worker_team",
                "client_name", "task_description", "estimated_hours",
                "actual_hours", "diff_hours"
            ]].rename(columns={
                "start_time": "시작 보고시각",
                "worker_name": "담당자",
                "worker_team": "소속팀",
                "client_name": "고객사",
                "task_description": "작업내용",
                "estimated_hours": "예정(h)",
                "actual_hours": "실제소요(h)",
                "diff_hours": "초과시간(+h)"
            }),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="overdue_tasks_table"
        )

        # 사용자가 행을 클릭했을 때 나타나는 카카오톡 원본 & 괴리 분석 박스
        if sel_overdue and hasattr(sel_overdue, "selection") and sel_overdue.selection.rows:
            sel_idx = sel_overdue.selection.rows[0]
            sel_row = overdue_df.iloc[sel_idx]
            
            st.markdown("---")
            st.markdown(f"#### 🔍 [선택 작업 괴리 분석] **{sel_row['worker_name']}** - **{sel_row['client_name']}** (`{sel_row['task_description']}`)")
            
            c_est, c_act, c_diff = st.columns(3)
            with c_est:
                st.metric("예정 시간", f"{sel_row['estimated_hours']}시간")
            with c_act:
                st.metric("실제 소요시간", f"{sel_row['actual_hours']}시간", delta=f"+{sel_row['diff_hours']}h 초과 지연", delta_color="inverse")
            with c_diff:
                st.metric("보고 일시", f"{sel_row['start_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(sel_row['start_time']) else ''}")

            st_time = sel_row['start_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(sel_row['start_time']) else ''
            ed_time = sel_row['end_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(sel_row['end_time']) else ''

            st.markdown(f"**💬 카카오톡 시작 보고 원본 메시지 ({st_time}):**")
            st.code(sel_row.get("raw_start_message", "(원본 없음)"), language="text")

            ed_label = f" ({ed_time})" if ed_time else ""
            st.markdown(f"**💬 카카오톡 완료 보고 원본 메시지{ed_label} (실제 지연/괴리 사유 확인):**")
            st.code(sel_row.get("raw_end_message", "(완료 메시지 없음 - 예정시간 초과로 인한 자동완료 처리)"), language="text")

        # 전수 아코디언도 제공
        with st.expander(f"💬 전체 초과 작업 카카오톡 원본 메시지 전수 보기 ({len(overdue_df)}건)", expanded=False):
            for i, (_, r) in enumerate(overdue_df.iterrows()):
                st.markdown(f"**[초과작업 #{i+1}] {r['start_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(r['start_time']) else ''} | {r['worker_name']} - {r['client_name']} ({r['task_description']}) [예정: {r['estimated_hours']}h ➔ 소요: {r['actual_hours']}h (🚨 +{r['diff_hours']}h 초과)]**")
                st.code(format_raw_chat_display(r), language="text")
                st.divider()



@st.dialog("👤 팀원 전체 작업 상세 내역", width="large")
def show_worker_all_tasks_dialog(worker_name: str, df_data: pd.DataFrame):
    w_df = df_data[df_data["worker_name"] == worker_name].sort_values(by="start_time", ascending=False).reset_index(drop=True)
    if w_df.empty:
        st.info(f"[{worker_name}] 님의 작업 데이터가 없습니다.")
        return

    tot_h = round(w_df["actual_hours"].sum(), 1)
    tot_cnt = len(w_df)
    night_cnt = int(((w_df["is_weekend_work"] == False) & (w_df["is_night_work"] == True)).sum())
    weekend_cnt = int(w_df["is_weekend_work"].sum())
    day_cnt = tot_cnt - night_cnt - weekend_cnt
    
    st.markdown(f"### 👤 **{worker_name}** 님의 전체 작업 내역 (총 **{tot_h}시간** / **{tot_cnt}건**)")
    st.markdown(f"☀️ 평일 주간: **{day_cnt}건** | 🌙 평일 야간: **{night_cnt}건** | 🏖️ 주말: **{weekend_cnt}건**")
    
    st.caption("💡 표에서 행을 클릭하시면 해당 작업의 **카카오톡 시작/완료 보고 원본 대화**가 아래에 표시됩니다.")
    sel_tbl = st.dataframe(
        w_df[[
            "start_time", "client_name", "task_description",
            "estimated_hours", "actual_hours", "status", "is_night_work", "is_weekend_work"
        ]].rename(columns={
            "start_time": "시작 보고시각",
            "client_name": "고객사",
            "task_description": "작업내용",
            "estimated_hours": "예정(h)",
            "actual_hours": "소요(h)",
            "status": "상태",
            "is_night_work": "야간여부",
            "is_weekend_work": "주말여부"
        }),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"worker_all_tasks_table_{worker_name}"
    )

    if sel_tbl and hasattr(sel_tbl, "selection") and sel_tbl.selection.rows:
        sel_row = w_df.iloc[sel_tbl.selection.rows[0]]
        st.markdown(f"##### 💬 [{sel_row['worker_name']} | {sel_row['client_name']}] 카카오톡 대화 원본")
        st.code(format_raw_chat_display(sel_row), language="text")

    with st.expander(f"💬 전체 작업 카카오톡 원본 메시지 전수 보기 ({len(w_df)}건)", expanded=False):
        for i, (_, r) in enumerate(w_df.iterrows()):
            st.markdown(f"**[작업 #{i+1}] {r['start_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(r['start_time']) else ''} | {r['client_name']} - {r['task_description']} ({r['actual_hours']}h)**")
            st.code(format_raw_chat_display(r), language="text")
            st.divider()


@st.dialog("🔍 작업 구분별 세부 내역", width="large")
def show_worker_category_tasks_dialog(worker_name: str, category: str, df_data: pd.DataFrame):
    w_df = df_data[df_data["worker_name"] == worker_name].copy()
    
    if "주말" in category:
        cat_df = w_df[w_df["is_weekend_work"] == True].sort_values(by="start_time", ascending=False).reset_index(drop=True)
        cat_icon = "🏖️"
        cat_name = "주말 작업 (야간포함)"
    elif "야간" in category:
        cat_df = w_df[(w_df["is_weekend_work"] == False) & (w_df["is_night_work"] == True)].sort_values(by="start_time", ascending=False).reset_index(drop=True)
        cat_icon = "🌙"
        cat_name = "평일 야간 작업 (19시~08시)"
    else:
        cat_df = w_df[(w_df["is_weekend_work"] == False) & (w_df["is_night_work"] == False)].sort_values(by="start_time", ascending=False).reset_index(drop=True)
        cat_icon = "☀️"
        cat_name = "평일 주간 작업"

    if cat_df.empty:
        st.info(f"[{worker_name}] 님의 [{cat_icon} {cat_name}]에 해당하는 작업 데이터가 없습니다.")
        return

    tot_h = round(cat_df["actual_hours"].sum(), 1)
    tot_cnt = len(cat_df)
    
    st.markdown(f"### {cat_icon} **{worker_name}** 님의 **[{cat_name}]** 세부 내역 (총 **{tot_h}시간** / **{tot_cnt}건**)")
    st.caption("💡 표에서 행을 클릭하시면 해당 작업의 **카카오톡 시작/완료 보고 원본 대화**가 아래에 표시됩니다.")
    
    sel_tbl = st.dataframe(
        cat_df[[
            "start_time", "client_name", "task_description",
            "estimated_hours", "actual_hours", "status"
        ]].rename(columns={
            "start_time": "시작 보고시각",
            "client_name": "고객사",
            "task_description": "작업내용",
            "estimated_hours": "예정(h)",
            "actual_hours": "소요(h)",
            "status": "상태"
        }),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"worker_cat_table_{worker_name}_{category}"
    )

    if sel_tbl and hasattr(sel_tbl, "selection") and sel_tbl.selection.rows:
        sel_row = cat_df.iloc[sel_tbl.selection.rows[0]]
        st.markdown(f"##### 💬 [{sel_row['worker_name']} | {sel_row['client_name']}] 카카오톡 대화 원본")
        st.code(format_raw_chat_display(sel_row), language="text")

    with st.expander(f"💬 전체 [{cat_name}] 카카오톡 원본 메시지 전수 보기 ({len(cat_df)}건)", expanded=False):
        for i, (_, r) in enumerate(cat_df.iterrows()):
            st.markdown(f"**[작업 #{i+1}] {r['start_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(r['start_time']) else ''} | {r['client_name']} - {r['task_description']} ({r['actual_hours']}h)**")
            st.code(format_raw_chat_display(r), language="text")
            st.divider()



def render_team_management_page(all_workers_list, team_mappings):
    """[⚙️ 팀원 소속 및 직급 관리] 전용 관리 페이지 (소속팀 + 직급 완벽 지원)"""
    st.header("⚙️ 팀원 소속 및 직급 관리")
    st.markdown("회사 4대 팀(`기술 1팀`, `기술 2팀`, `기술 3팀`, `PI팀`)별로 팀원의 **소속팀과 4대 직급(`사원`, `대리`, `과장`, `수석`)**을 배정하고 자유롭게 수정/해제할 수 있습니다.")
    st.divider()

    COMPANY_TITLES = ["사원", "대리", "과장", "수석"]
    members_info = TeamService.get_team_members_info()

    col_assign, col_status = st.columns([1.1, 0.9])

    # 1. 팀원별 소속팀 & 직급 개별 간편 설정
    with col_assign:
        st.markdown("### 📥 1. 팀원별 소속팀 & 직급 빠른 설정")
        st.caption("팀원을 선택하고 소속팀과 직급을 지정한 뒤 저장하시면 **DB와 작업 원장에 즉시 동기화**됩니다.")
        
        if all_workers_list:
            pick_worker = st.selectbox("1️⃣ 담당자 선택:", options=all_workers_list, key="pick_worker_manage")
            
            cur_worker_team = members_info.get(pick_worker, {}).get("team", "기술 1팀")
            cur_worker_title = members_info.get(pick_worker, {}).get("title", "")
            
            team_idx = DEFAULT_TEAMS.index(cur_worker_team) if cur_worker_team in DEFAULT_TEAMS else 0
            
            c_sel1, c_sel2 = st.columns(2)
            with c_sel1:
                sel_team = st.selectbox("2️⃣ 소속 팀 지정:", options=DEFAULT_TEAMS + [UNASSIGNED_TEAM], index=team_idx if team_idx < len(DEFAULT_TEAMS) else 0, key="sel_team_manage")
            with c_sel2:
                avail_titles = COMPANY_TITLES + ["(미지정)"]
                title_idx = COMPANY_TITLES.index(cur_worker_title) if cur_worker_title in COMPANY_TITLES else (len(avail_titles) - 1)
                
                sel_title = st.selectbox("3️⃣ 직급 선택 (4대 직급):", options=avail_titles, index=title_idx, key="sel_title_manage")

            final_title = "" if sel_title == "(미지정)" else sel_title.strip()

            if st.button("💾 소속팀 및 직급 즉시 저장 ⚡", use_container_width=True, type="primary"):
                TeamService.save_worker_info(pick_worker, sel_team, final_title)
                st.toast(f"🎉 [{pick_worker}] 님의 정보가 [{sel_team} | {final_title or '직급 미지정'}]으로 저장되었습니다!", icon="✅")
                st.rerun()

    # 2. 팀별 소속 인원 및 직급 현황
    with col_status:
        st.markdown("### 🏢 2. 팀별 소속 인원 & 직급 현황")
        
        # 4대 팀 현황
        for t_name in DEFAULT_TEAMS:
            m_list = [w for w in all_workers_list if members_info.get(w, {}).get("team", "") == t_name]
            with st.expander(f"🔹 {t_name} (총 {len(m_list)}명)", expanded=True if len(m_list) > 0 else False):
                if m_list:
                    st.caption("💡 각 팀원의 **직급을 선택하면 즉시 자동 저장⚡**되며, **[❌ 해제]**를 누르면 팀에서 제외됩니다.")
                    
                    # 2열 그리드로 팀원별 [이름 + 직급 셀렉트박스 + 개별 해제] 배치
                    grid_cols = st.columns(2)
                    for idx, name in enumerate(m_list):
                        cur_j_title = members_info.get(name, {}).get("title", "")
                        with grid_cols[idx % 2]:
                            c_name, c_title, c_del = st.columns([1.5, 2.0, 1.0])
                            with c_name:
                                st.markdown(f"<div style='padding-top:6px;'>👤 <b><code>{name}</code></b></div>", unsafe_allow_html=True)
                            with c_title:
                                title_opts = ["(미지정)", "사원", "대리", "과장", "수석"]
                                t_idx = title_opts.index(cur_j_title) if cur_j_title in title_opts else 0
                                new_t = st.selectbox(
                                    "직급",
                                    options=title_opts,
                                    index=t_idx,
                                    label_visibility="collapsed",
                                    key=f"team_direct_title_{t_name}_{name}"
                                )
                                final_new_t = "" if new_t == "(미지정)" else new_t
                                if final_new_t != cur_j_title:
                                    TeamService.update_worker_title(name, final_new_t)
                                    st.toast(f"⚡ [{name}] 님의 직급이 [{final_new_t or '미지정'}]으로 자동 저장되었습니다!", icon="✅")
                                    st.rerun()
                            with c_del:
                                if st.button("❌ 해제", key=f"del_indiv_{t_name}_{name}", help=f"[{name}] 님을 {t_name}에서 해제합니다."):
                                    TeamService.remove_worker_team(name)
                                    st.toast(f"🗑️ [{name}] 님의 {t_name} 소속이 해제되었습니다!", icon="✅")
                                    st.rerun()
                    
                    st.divider()
                    col_btn_clear, _ = st.columns([1, 1])
                    with col_btn_clear:
                        if st.button(f"🗑️ {t_name} 소속 전체 일괄 해제", key=f"clear_all_{t_name}"):
                            TeamService.clear_team_all_members(t_name)
                            st.warning(f"{t_name} 소속 팀원이 모두 해제되었습니다.")
                            st.rerun()
                else:
                    st.info(f"현재 {t_name}에 등록된 팀원이 없습니다.")

        # 미지정 현황
        unassigned_list = [w for w in all_workers_list if members_info.get(w, {}).get("team", UNASSIGNED_TEAM) == UNASSIGNED_TEAM]
        with st.expander(f"⚪ 소속 미지정 (총 {len(unassigned_list)}명)", expanded=True if len(unassigned_list) > 0 else False):
            if unassigned_list:
                items_str = [f"`{name}`" for name in unassigned_list]
                st.markdown("**미지정 인원:** " + ", ".join(items_str))
            else:
                st.success("모든 팀원이 4대 팀에 배정되어 있습니다.")

    st.divider()

    # 3. 테이블형 팀원 소속 & 직급 일괄 수정 / 삭제 에디터
    st.markdown("### 📋 3. 전체 팀원 소속 & 직급 일괄 수정 테이블")
    st.caption("아래 표에서 각 팀원의 **소속팀**과 **직급(사원/대리/과장/수석)**을 드롭다운으로 변경한 후 하단의 **[💾 표 수정 내용 전체 저장]** 버튼을 누르시면 한 번에 저장됩니다.")
    
    mapping_data = []
    for w in all_workers_list:
        w_info = members_info.get(w, {})
        cur_t = w_info.get("title", "")
        mapping_data.append({
            "담당자": w,
            "소속팀": w_info.get("team", UNASSIGNED_TEAM),
            "직급": cur_t if cur_t in COMPANY_TITLES else ""
        })
    mapping_df = pd.DataFrame(mapping_data)
    
    edited_df = st.data_editor(
        mapping_df,
        column_config={
            "담당자": st.column_config.TextColumn("담당자", disabled=True),
            "소속팀": st.column_config.SelectboxColumn(
                "소속팀",
                options=DEFAULT_TEAMS + [UNASSIGNED_TEAM],
                required=True,
                help="원하는 팀으로 변경하거나 '미지정'을 선택하여 소속을 삭제합니다."
            ),
            "직급": st.column_config.SelectboxColumn(
                "직급",
                options=["사원", "대리", "과장", "수석", ""],
                required=False,
                help="사원, 대리, 과장, 수석 중 선택하세요."
            )
        },
        use_container_width=True,
        hide_index=True,
        key="team_data_editor_with_titles"
    )
    
    if st.button("💾 표 수정 내용 전체 저장", use_container_width=True, type="primary"):
        for _, row in edited_df.iterrows():
            w_name = row["담당자"]
            t_name = row["소속팀"]
            j_title = str(row["직급"]).strip() if pd.notna(row["직급"]) and str(row["직급"]).strip() != "None" else ""
            TeamService.save_worker_info(w_name, t_name, j_title)
        st.success("🎉 모든 팀원의 소속팀 및 직급 정보가 성공적으로 일괄 업데이트되었습니다!")
        st.rerun()


def main():
    importlib.reload(kakao_parser)
    importlib.reload(reply_matcher)
    importlib.reload(team_service)
    importlib.reload(supabase_client)
    from src.parser.reply_matcher import WorkLogMatcher

    df_raw = load_data()
    team_mappings = TeamService.get_team_mappings()
    all_workers_list = sorted(df_raw["worker_name"].dropna().unique()) if not df_raw.empty else []

    # ==========================================
    # 사이드바: 최상단 메인 메뉴 선택 (대시보드 vs 팀원 소속 관리)
    # ==========================================
    with st.sidebar:
        st.markdown('<div class="sidebar-section-header purple">📌 메인 메뉴</div>', unsafe_allow_html=True)
        selected_menu = st.radio(
            "이동할 메뉴를 선택하세요:",
            [
                "📊 실시간 분석 대시보드",
                "⚙️ 팀원 소속 관리 (기술 1/2/3팀, PI팀)",
                "📋 작업 기록 원장 & 엑셀"
            ],
            index=0,
            label_visibility="collapsed"
        )
        st.write("")

    # 상단 컴팩트 헤더 (화면 최상단 밀착 배치)
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    st.markdown(f"""
    <div class="dashboard-title-box">
        <div>
            <div class="main-title-text">
                📊 팀 지원 시간 & 업무량 분석 대시보드
                <span style="font-size: 13px; color: #64748B; font-weight: 500; margin-left: 6px;">(기준 시각: {current_time_str})</span>
            </div>
            <div style="font-size: 13px; color: #94A3B8; margin-top: 4px;">카카오톡 작업/지원 보고 데이터를 기반으로 월별 업무 투입 공수 및 사용자별 업무량을 모니터링합니다.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ==========================================
    # 메뉴 분기 1: [⚙️ 팀원 소속 관리] 메뉴 선택 시
    # ==========================================
    if "팀원 소속 관리" in selected_menu:
        render_team_management_page(all_workers_list, team_mappings)
        return

    # ==========================================
    # 메뉴 분기 2 & 3: 사이드바 필터 및 대시보드
    # ==========================================
    # 메뉴 분기 2 & 3: 사이드바 필터 및 대시보드
    # ==========================================
    with st.sidebar:
        # 1. 핵심 조회 기준 필터
        if not df_raw.empty:
            st.markdown('<div class="sidebar-section-header">🔍 핵심 조회 기준</div>', unsafe_allow_html=True)
            
            # (1) 대상 월 선택
            available_months = sorted(df_raw["month_str"].dropna().unique(), reverse=True)
            month_mode = st.selectbox(
                "📅 대상 기간:",
                ["특정 월 선택 (기본)", "전체 기간", "다중 월 선택"],
                index=0
            )
            
            selected_months = []
            if month_mode == "전체 기간":
                selected_months = available_months
            elif month_mode == "특정 월 선택 (기본)":
                single_month = st.selectbox("조회할 월:", options=available_months, index=0, label_visibility="collapsed")
                selected_months = [single_month] if single_month else available_months
            else:
                selected_months = st.multiselect("조회할 월(다중):", options=available_months, default=available_months, label_visibility="collapsed")

            # (2) 소속 팀 선택 (기본값: 기술 1팀)
            team_filter_options = ["전체 팀"] + DEFAULT_TEAMS
            default_team_idx = team_filter_options.index("기술 1팀") if "기술 1팀" in team_filter_options else 0
            selected_team = st.selectbox("🏢 소속 팀:", options=team_filter_options, index=default_team_idx)

            # 선택된 팀에 소속된 팀원 목록 필터링
            if selected_team == "전체 팀":
                team_available_workers = all_workers_list
            else:
                team_available_workers = [w for w in all_workers_list if team_mappings.get(w, "") == selected_team]
                if not team_available_workers:
                    team_available_workers = sorted(df_raw[df_raw["worker_team"] == selected_team]["worker_name"].dropna().unique())

            # (3) 사용자(팀원) 선택
            worker_target_type = st.selectbox(
                "👤 담당 팀원:",
                [f"{selected_team} 전체 인원 (기본)", "특정 팀원 직접 선택"],
                index=0
            )
            
            selected_workers = []
            if worker_target_type == f"{selected_team} 전체 인원 (기본)":
                worker_mode = "팀 전체 인원"
                selected_workers = team_available_workers
            else:
                worker_mode = "특정 사용자 선택"
                selected_workers = st.multiselect(
                    f"팀원 선택 ({selected_team}):",
                    options=team_available_workers,
                    default=[team_available_workers[0]] if team_available_workers else [],
                    label_visibility="collapsed"
                )

            # (4) 추가 상세 필터 (접이식 아코디언으로 정돈)
            with st.expander("🎯 추가 상세 필터 (고객사 / 작업구분 / 직급 / 야간·주말)", expanded=False):
                # 고객사 선택
                available_clients = sorted(df_raw["client_name"].dropna().unique())
                client_mode = st.radio("🏢 고객사 범위:", ["전체 고객사", "특정 고객사 선택"], horizontal=True)
                selected_clients = available_clients if client_mode == "전체 고객사" else st.multiselect("고객사 선택:", options=available_clients, default=available_clients, label_visibility="collapsed")

                # 작업구분 필터
                available_types = sorted(df_raw["log_type"].dropna().unique())
                type_mode = st.radio("🏷️ 작업 구분:", ["전체 구분", "특정 구분 선택"], horizontal=True)
                selected_types = available_types if type_mode == "전체 구분" else st.multiselect("작업 구분 선택:", options=available_types, default=available_types, label_visibility="collapsed")

                # 👔 직급 필터 (사원 / 대리 / 과장 / 수석)
                title_mode = st.radio("👔 직급 범위:", ["전체 직급", "특정 직급 선택"], horizontal=True)
                selected_titles = ["사원", "대리", "과장", "수석"] if title_mode == "전체 직급" else st.multiselect("직급 선택:", options=["사원", "대리", "과장", "수석"], default=["사원", "대리", "과장", "수석"], label_visibility="collapsed")

                # 야간/주말 필터
                night_only = st.checkbox("🌙 야간 작업만 보기 (19시~08시)")
                weekend_only = st.checkbox("🏖️ 주말 작업만 보기")

            # 필터 적용
            df = df_raw.copy()
            
            # 최신 직급 매핑 동기화
            title_map = TeamService.get_title_mappings()
            df["worker_title"] = df["worker_name"].map(title_map).fillna(df.get("worker_title", ""))
            
            if selected_months:
                df = df[df["month_str"].isin(selected_months)]
            else:
                df = df.iloc[0:0]

            if selected_team != "전체 팀":
                df = df[df["worker_name"].isin(team_available_workers)]

            if selected_workers:
                df = df[df["worker_name"].isin(selected_workers)]
            else:
                df = df.iloc[0:0]

            if selected_clients:
                df = df[df["client_name"].isin(selected_clients)]
            else:
                df = df.iloc[0:0]

            if selected_types:
                df = df[df["log_type"].isin(selected_types)]
            else:
                df = df.iloc[0:0]

            # 직급 필터링 적용
            if title_mode != "전체 직급":
                df = df[df["worker_title"].isin(selected_titles)]

            if night_only:
                df = df[df["is_night_work"] == True]
            if weekend_only:
                df = df[df["is_weekend_work"] == True]
        else:
            df = df_raw.copy()
            selected_months = []
            selected_team = "전체 팀"
            selected_workers = []
            worker_mode = "팀 전체 인원"
            title_mode = "전체 직급"
            selected_titles = []
            team_available_workers = []

        # 2. 카카오톡 실시간 동기화
        st.markdown('<div class="sidebar-section-header green">🤖 카카오톡 실시간 연동</div>', unsafe_allow_html=True)
        countdown = get_collector_countdown_info()
        st.components.v1.html(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    background: transparent;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    overflow: hidden;
                }}
                .sb-card {{
                    background: rgba(0, 230, 118, 0.08);
                    border: 1px solid rgba(0, 230, 118, 0.35);
                    border-radius: 8px;
                    padding: 7px 10px;
                    box-sizing: border-box;
                }}
                .sb-title {{
                    font-weight: 800;
                    color: #00E676;
                    font-size: 11.5px;
                }}
                .sb-main {{
                    font-size: 13.5px;
                    font-weight: 900;
                    color: #FFFFFF;
                    margin-top: 2px;
                }}
                .sb-sub {{
                    font-size: 10.5px;
                    color: #94A3B8;
                    margin-top: 2px;
                }}
            </style>
        </head>
        <body>
            <div class="sb-card">
                <div class="sb-title">⏳ 다음 자동 증분 수집:</div>
                <div class="sb-main">
                    <span id="sb-live-timer">{countdown['remaining_minutes']}분 뒤</span> <span style="font-size: 11px; color: #00E5FF; font-weight: 700;">({countdown['next_run_str']} 예정)</span>
                </div>
                <div class="sb-sub">최근 수집: {countdown['last_run_str']} | 10분 주기 자동</div>
            </div>
            <script>
                let targetTs = {countdown['target_timestamp']};
                function updateSb() {{
                    let nowTs = Math.floor(Date.now() / 1000);
                    let diff = targetTs - nowTs;
                    let tEl = document.getElementById('sb-live-timer');
                    if (!tEl) return;
                    if (diff <= 0) {{
                        tEl.innerText = "⚡ 지금 수집 중...";
                        tEl.style.color = "#00E676";
                    }} else {{
                        let m = Math.floor(diff / 60);
                        let s = diff % 60;
                        let sStr = s < 10 ? '0' + s : s;
                        tEl.innerText = (m > 0 ? m + "분 " : "") + sStr + "초 뒤";
                        tEl.style.color = "#FFFFFF";
                    }}
                }}
                setInterval(updateSb, 1000);
                updateSb();
            </script>
        </body>
        </html>
        """, height=72)

        if st.button("⚡ [기술본부] 방 지금 즉시 긁어오기", key="btn_manual_kakao_sidebar", type="primary", use_container_width=True, help="PC 카카오톡에 열려 있는 '[기술본부] 업무공유방' 창에서 최신 대화를 즉시 긁어와 DB에 저장/동기화합니다."):
            with st.spinner("💬 카카오톡 [기술본부] 업무공유방에서 최신 대화 긁어오는 중..."):
                res = run_collection_cycle(is_manual=True)
                if res.get("status") == "success":
                    st.toast(f"🎉 즉시 수집 완료! 총 {res['total_records']}건 분석 (DB 저장: {res['saved_records']}건)", icon="✅")
                    st.success(f"🎉 즉시 수집 성공! 총 {res['total_records']}건 분석 (DB 저장/동기화: {res['saved_records']}건)")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                elif res.get("status") == "window_not_found":
                    st.toast("⚠️ 카카오톡 대화방 창을 찾을 수 없습니다.", icon="❌")
                    st.error("⚠️ '🚩✨[기술본부] 업무공유방' 창을 찾을 수 없습니다.\n\n💡 **PC 카카오톡에서 해당 대화방 창을 열어둔 상태**에서 다시 눌러주세요!")
                elif res.get("status") == "no_text":
                    st.warning("⚠️ 대화창에서 텍스트를 읽지 못했습니다. 카톡 대화방을 마우스로 한 번 클릭한 뒤 다시 눌러주세요.")
                else:
                    st.info(f"💡 {res.get('message', '수집 완료')}")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()

        # 3. 데이터 수동 동기화 (대화 파일 업로드)
        st.markdown('<div class="sidebar-section-header blue">📥 데이터 동기화 (파일 업로드)</div>', unsafe_allow_html=True)
        with st.expander("💬 카카오톡 대화 파일 업로드 (.txt)", expanded=False):
            uploaded_file = st.file_uploader("카카오톡 대화 텍스트 파일", type=["txt"], label_visibility="collapsed")
            if uploaded_file is not None:
                try:
                    file_content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
                    records = WorkLogMatcher.parse_and_match_text(file_content)
                    if records:
                        clear_all_caches_and_db()
                        saved = db_manager.save_work_logs(records)
                        st.success(f"총 {len(records)}건 최신 엔진으로 완벽 동기화 완료!")
                        st.rerun()
                    else:
                        st.warning("파싱 가능한 작업/지원 메시지가 없습니다. 파일 내용을 확인해주세요.")
                except Exception as e:
                    st.error(f"파일 처리 중 오류: {e}")

        # 4. 시스템 관리
        st.markdown('<div class="sidebar-section-header amber">⚙️ 시스템 관리</div>', unsafe_allow_html=True)
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🔄 새로고침", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
        with col_btn2:
            if st.button("🗑️ 전체 초기화", use_container_width=True, help="기존 누적 데이터와 캐시를 모두 초기화합니다."):
                clear_all_caches_and_db()
                st.toast("🧹 DB 및 캐시가 완전히 초기화되었습니다!", icon="✅")
                st.warning("DB 및 모든 캐시가 초기화되었습니다.")
                st.rerun()

    # 데이터가 없을 때 안내 화면
    if df_raw.empty:
        st.warning("⚠️ 현재 등록된 작업 로그 데이터가 없습니다.")
        st.info("💡 사이드바의 **[카카오톡 대화 파일 업로드]**를 통해 대화 텍스트(.txt)를 업로드하거나, PC 카카오톡 자동 수집기를 실행해주세요.")
        return

    # ==========================================
    # 메뉴 분기 3: [📋 작업 기록 원장 & 엑셀] 메뉴 선택 시
    # ==========================================
    if "작업 기록 원장" in selected_menu:
        st.subheader("📋 작업 지원 상세 기록 원장 & 엑셀 다운로드")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name="지원시간통계")
        excel_data = output.getvalue()
        
        btn_col1, btn_col2 = st.columns([1, 4])
        with btn_col1:
            st.download_button(
                label="📥 엑셀(.xlsx) 다운로드",
                data=excel_data,
                file_name=f"작업지원시간_통계_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with btn_col2:
            st.download_button(
                label="📥 CSV 다운로드",
                data=df.to_csv(index=False, encoding='utf-8-sig'),
                file_name=f"작업지원시간_통계_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        display_cols = [
            "start_time", "status", "log_type", "worker_name", "worker_company", "worker_team",
            "client_name", "task_description", "estimated_hours", "actual_hours", "is_night_work", "is_weekend_work"
        ]
        available_display_cols = [c for c in display_cols if c in df.columns]
        
        st.dataframe(
            df[available_display_cols].rename(columns={
                "start_time": "시작 보고시각",
                "status": "상태",
                "log_type": "구분",
                "worker_name": "담당자",
                "worker_company": "소속",
                "worker_team": "소속팀",
                "client_name": "고객사",
                "task_description": "작업내용",
                "estimated_hours": "예정(h)",
                "actual_hours": "소요(h)",
                "is_night_work": "야간여부",
                "is_weekend_work": "주말여부"
            }),
            use_container_width=True,
            hide_index=True
        )
        return

    # ==========================================
    # 메뉴 분기 1: [📊 실시간 분석 대시보드] 메인 화면
    # ==========================================
    month_desc = ", ".join(selected_months) if len(selected_months) <= 2 else f"{selected_months[0]} 외 {len(selected_months)-1}개 월"
    if len(selected_months) == len(available_months):
        month_desc = "전체 기간"

    if worker_mode == "팀 전체 인원":
        if selected_team != "전체 팀":
            worker_desc = f"{selected_team} 전체 ({len(team_available_workers)}명)"
        else:
            worker_desc = f"전체 인원 ({len(all_workers_list)}명)"
    else:
        worker_desc = ", ".join(selected_workers) if len(selected_workers) <= 3 else f"{selected_workers[0]} 외 {len(selected_workers)-1}명"

    title_badge_str = ""
    if title_mode != "전체 직급" and selected_titles:
        title_badge_str = f" | <b>직급 [{', '.join(selected_titles)}]</b>"

    # 메인 상단 집계 기준 배너 (가로 전체 너비로 시원하게 렌더링)
    st.markdown(
        f'<div class="filter-badge">📌 현재 집계 기준: <b>기간 [{month_desc}]</b> | <b>소속 [{selected_team}]</b> | <b>사용자 [{worker_desc}]</b>{title_badge_str} (총 {len(df)}건 일치)</div>',
        unsafe_allow_html=True
    )

    # 핵심 KPI 카드 (프리미엄 네온 글래스모피즘 카드 렌더링)
    kpi = StatsService.compute_kpis(df)
    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)
    
    with kpi_col1:
        st.markdown(f"""
        <div class="kpi-card" style="border-top: 4px solid #00E5FF;">
            <div class="kpi-title">⏱️ 총 지원 시간</div>
            <div class="kpi-value" style="color: #00E5FF;">{kpi['total_hours']:,}<span class="kpi-unit">시간</span></div>
            <div class="kpi-badge badge-cyan">⚡ 실시간 합산 집계</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔍 상세 내역 팝업", key="btn_kpi_hours", use_container_width=True):
            show_kpi_total_hours_dialog(df)
        
    with kpi_col2:
        st.markdown(f"""
        <div class="kpi-card" style="border-top: 4px solid #00E676;">
            <div class="kpi-title">📋 총 작업 건수</div>
            <div class="kpi-value" style="color: #FFFFFF;">{kpi['total_tasks']:,}<span class="kpi-unit">건</span></div>
            <div class="kpi-badge badge-green">🟢 완료 {kpi['completed_tasks']}건 <span style="color:#64748B;">|</span> 🟡 진행 {kpi['pending_tasks']}건</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔍 건수 상세 팝업", key="btn_kpi_tasks", use_container_width=True):
            show_kpi_total_tasks_dialog(df)
        
    with kpi_col3:
        st.markdown(f"""
        <div class="kpi-card" style="border-top: 4px solid #B388FF;">
            <div class="kpi-title">👥 투입 인원 & 평균 공수</div>
            <div class="kpi-value" style="color: #FFFFFF;">{kpi['active_workers']}<span class="kpi-unit">명</span></div>
            <div class="kpi-badge badge-purple">👤 1인당 평균 {kpi['avg_hours_per_worker']}h</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔍 팀원별 공수 팝업", key="btn_kpi_workers", use_container_width=True):
            show_kpi_workers_dialog(df)
        
    with kpi_col4:
        total_urg = kpi['night_tasks_count'] + kpi['weekend_tasks_count']
        st.markdown(f"""
        <div class="kpi-card" style="border-top: 4px solid #FFAB00;">
            <div class="kpi-title">🌙 야간 / 주말 긴급 작업</div>
            <div class="kpi-value" style="color: #FFAB00;">{total_urg}<span class="kpi-unit">건</span></div>
            <div class="kpi-badge badge-amber">🌙 야간 {kpi['night_tasks_count']}건 <span style="color:#64748B;">|</span> 🏖️ 주말 {kpi['weekend_tasks_count']}건</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔍 긴급 작업 팝업", key="btn_kpi_urgent", use_container_width=True):
            show_kpi_urgent_dialog(df)
        
    with kpi_col5:
        overdue_val = float(kpi.get('overdue_rate', 0))
        overdue_color = "#FF5252" if overdue_val > 10 else "#00E676"
        badge_cls = "badge-red" if overdue_val > 10 else "badge-green"
        st.markdown(f"""
        <div class="kpi-card" style="border-top: 4px solid {overdue_color};">
            <div class="kpi-title">⚠️ 예정 시간 초과율</div>
            <div class="kpi-value" style="color: {overdue_color};">{kpi['overdue_rate']}<span class="kpi-unit">%</span></div>
            <div class="kpi-badge {badge_cls}">🚨 초과 {kpi['overdue_tasks_count']}건 발생</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔍 초과 내역 팝업", key="btn_kpi_overdue", use_container_width=True):
            show_kpi_overdue_dialog(df)

    # ----------------------------------------------------
    # 🚨 상단 과중 근무 실시간 감지 & 원클릭 보상휴가 팝업 배너
    # ----------------------------------------------------
    if not df.empty and "week_label" in df.columns:
        all_rewards = RewardLeaveService.get_all_reward_leaves()
        overwork_items = []
        
        # 주차별/팀원별 집계
        wk_user_agg = df.groupby(["worker_name", "week_label"])["actual_hours"].sum().reset_index()
        for _, r in wk_user_agg.iterrows():
            w_name = r["worker_name"]
            w_lbl = r["week_label"]
            val = round(r["actual_hours"], 1)
            short_w = w_lbl.split(" ")[-2] if " " in w_lbl else w_lbl
            if val >= 40.0:
                if (w_name, w_lbl) not in all_rewards:
                    overwork_items.append({
                        "worker_name": w_name,
                        "week_label": w_lbl,
                        "short_w": short_w,
                        "val": val,
                        "is_52": (val >= 52.0)
                    })

        if overwork_items:
            danger_items = [it for it in overwork_items if it["is_52"]]
            caution_items = [it for it in overwork_items if not it["is_52"]]

            with st.container(border=True):
                # 1행: 상단 알림 제목 (반짝반짝 애니메이션) + 우측 퀵점프 바로가기 버튼
                col_head_l, col_head_r = st.columns([7.8, 2.2])
                with col_head_l:
                    st.markdown('<div style="font-size: 15px; font-weight: 800; color: #FFFFFF; display: flex; align-items: center; gap: 8px;"><span class="siren-icon">🚨</span> <span class="alert-blink-badge">[과중 근무 발생 알림]</span> <span style="font-weight: 800; color: #FFFFFF;">선택 기간 내 주 40시간 / 52시간 초과 팀원이 감지되었습니다!</span></div>', unsafe_allow_html=True)
                with col_head_r:
                    st.markdown('<div style="text-align: right;"><a href="#weekly-monitor-section" style="background: linear-gradient(135deg, #FF1744, #D50000); color: #FFFFFF; font-weight: 800; font-size: 12.5px; padding: 7px 16px; border-radius: 8px; text-decoration: none; display: inline-flex; align-items: center; gap: 4px; box-shadow: 0 4px 12px rgba(255, 23, 68, 0.45); white-space: nowrap;">👇 주차별 모니터링 표로 바로가기</a></div>', unsafe_allow_html=True)

                st.markdown("<div style='margin-top: 6px; margin-bottom: 10px; border-top: 1px solid rgba(255, 82, 82, 0.3);'></div>", unsafe_allow_html=True)
                
                # 2행: 🚨 주 52h 초과 위험 팀원들 (있을 경우)
                if danger_items:
                    col_d_lbl, col_d_chips = st.columns([2.0, 8.0])
                    with col_d_lbl:
                        st.markdown(f"<div style='padding-top:4px; font-size:13px; font-weight:900; color:#FF5252;'>🚨 주 52h 초과 ({len(danger_items)}건):</div>", unsafe_allow_html=True)
                    with col_d_chips:
                        d_cols = st.columns(max(len(danger_items), 1) + 4)
                        for d_idx, d_item in enumerate(danger_items):
                            with d_cols[d_idx]:
                                if st.button(f"🚨 {d_item['worker_name']}({d_item['short_w']}:{d_item['val']}h)", key=f"btn_chip_danger_{d_item['worker_name']}_{d_item['week_label']}", help=f"[{d_item['worker_name']}] 보상 휴가 팝업 열기"):
                                    show_weekly_detail_dialog(d_item["worker_name"], df, default_week_name=d_item["week_label"])

                # 3행: ⚠️ 주 40h 초과 주의 팀원들 (있을 경우)
                if caution_items:
                    col_c_lbl, col_c_chips = st.columns([2.0, 8.0])
                    with col_c_lbl:
                        st.markdown(f"<div style='padding-top:4px; font-size:13px; font-weight:900; color:#FFA726;'>⚠️ 주 40h 초과 ({len(caution_items)}건):</div>", unsafe_allow_html=True)
                    with col_c_chips:
                        c_cols = st.columns(max(len(caution_items), 1) + 4)
                        for c_idx, c_item in enumerate(caution_items):
                            with c_cols[c_idx]:
                                if st.button(f"⚠️ {c_item['worker_name']}({c_item['short_w']}:{c_item['val']}h)", key=f"btn_chip_caution_{c_item['worker_name']}_{c_item['week_label']}", help=f"[{c_item['worker_name']}] 보상 휴가 팝업 열기"):
                                    show_weekly_detail_dialog(c_item["worker_name"], df, default_week_name=c_item["week_label"])
        else:
            # 🟢 과중 근무자가 없는 경우: 상하 여백이 100% 동일한 일체형 카드 배너
            st.markdown("""
            <div style="background: linear-gradient(135deg, rgba(0, 230, 118, 0.08), rgba(0, 229, 255, 0.05)); border: 1.5px solid rgba(0, 230, 118, 0.35); border-radius: 10px; padding: 10px 18px; margin: 10px 0 14px 0; display: flex; justify-content: space-between; align-items: center; width: 100%; box-sizing: border-box; box-shadow: 0 4px 16px rgba(0, 230, 118, 0.12);">
                <div style="font-size: 14.5px; font-weight: 700; color: #E2E8F0; display: flex; align-items: center; gap: 10px; margin: 0; padding: 0; line-height: 1;">
                    <span style="font-size: 16px; line-height: 1;">🟢</span>
                    <span style="background: rgba(0, 230, 118, 0.18); color: #00E676; border: 1.5px solid rgba(0, 230, 118, 0.6); padding: 3px 10px; border-radius: 6px; font-weight: 900; font-size: 13px; line-height: 1.2; display: inline-flex; align-items: center;">[과중 근무 없음]</span>
                    <span style="color: #94A3B8; font-size: 13.5px; line-height: 1;">현재 선택된 기간 내에 주 40시간 / 52시간을 초과한 과중 근무 팀원이 없습니다. (안정적인 근무 상태)</span>
                </div>
                <div style="margin: 0; padding: 0;">
                    <a href="#weekly-monitor-section" style="background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.2); color: #E2E8F0; font-weight: 700; font-size: 12px; padding: 6px 14px; border-radius: 8px; text-decoration: none; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; line-height: 1;">👇 주차별 모니터링 표</a>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # 탭 기반 분석 시각화
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "👤 팀원별 업무량 분석",
        "🏢 팀별 업무량 비교",
        "📈 월별/일별 추이",
        "🏢 고객사별 공수 분포",
        "⏱️ 예정 vs 실제 소요시간"
    ])

    # ------------------------------------------
    # TAB 1: 팀원별 업무량 분석
    # ------------------------------------------
    with tab1:
        st.subheader(f"👤 {selected_team} - 팀원별 총 작업 시간 및 업무 집중도 ({month_desc})")
        worker_summary = StatsService.get_worker_summary(df)
        
        if not worker_summary.empty:
            ctrl_col1, ctrl_col2 = st.columns([2, 1])
            with ctrl_col1:
                total_workers_cnt = len(worker_summary)
                view_options = ["전체 보기"]
                if total_workers_cnt > 15:
                    view_options.insert(0, "상위 15명")
                if total_workers_cnt > 30:
                    view_options.insert(1, "상위 30명")
                
                selected_view = st.radio("📊 표시 인원 범위:", options=view_options, horizontal=True)
            with ctrl_col2:
                chart_orientation = st.radio("📐 차트 방향:", options=["가로형 (이름 안 겹침 - 권장)", "세로형 (세로 90도 회전)"], horizontal=True)

            if selected_view == "상위 15명":
                display_summary = worker_summary.head(15).copy()
            elif selected_view == "상위 30명":
                display_summary = worker_summary.head(30).copy()
            else:
                display_summary = worker_summary.copy()

            st.caption("💡 **그래프의 막대(세그먼트)를 클릭**하시면, **[왼쪽 그래프: 개인 전체 작업 내역]**, **[오른쪽 그래프: 평일 주간/야간/주말별 상세 내역 및 카카오톡 원본]** 팝업이 바로 열립니다.")
            
            chart_height = max(450, len(display_summary) * 28)
            col_t1_left, col_t1_right = st.columns(2)
            
            event_left = None
            event_right = None

            if "가로형" in chart_orientation:
                with col_t1_left:
                    sorted_for_h_bar = display_summary.sort_values(by="total_hours", ascending=True)
                    fig_worker = px.bar(
                        sorted_for_h_bar,
                        x="total_hours",
                        y="worker_name",
                        orientation="h",
                        color="total_hours",
                        color_continuous_scale="Blues",
                        text="total_hours",
                        labels={"worker_name": "담당자", "total_hours": "총 투입 시간(h)"},
                        title=f"팀원별 총 지원 시간(h) 순위 ({selected_view})"
                    )
                    fig_worker.update_traces(
                        texttemplate='%{text}h',
                        textposition='outside',
                        customdata=[[w] for w in sorted_for_h_bar['worker_name']]
                    )
                    fig_worker.update_layout(
                        height=chart_height,
                        margin=dict(l=100, r=40, t=50, b=30),
                        yaxis=dict(tickfont=dict(size=12, family="Malgun Gothic, Arial"))
                    )
                    event_left = st.plotly_chart(fig_worker, use_container_width=True, on_select="rerun", selection_mode=["points"], key="chart_worker_left_h")

                with col_t1_right:
                    sorted_for_h_bar = display_summary.sort_values(by="total_hours", ascending=True)
                    fig_night = go.Figure(data=[
                        go.Bar(
                            name='☀️ 평일 주간',
                            y=sorted_for_h_bar['worker_name'],
                            x=sorted_for_h_bar.get('weekday_day_tasks', sorted_for_h_bar['total_tasks'] - sorted_for_h_bar['night_tasks'] - sorted_for_h_bar['weekend_tasks']),
                            orientation='h',
                            marker_color='#42A5F5',
                            customdata=[[w, '☀️ 평일 주간'] for w in sorted_for_h_bar['worker_name']]
                        ),
                        go.Bar(
                            name='🌙 평일 야간 (19시~08시)',
                            y=sorted_for_h_bar['worker_name'],
                            x=sorted_for_h_bar.get('weekday_night_tasks', sorted_for_h_bar['night_tasks']),
                            orientation='h',
                            marker_color='#E53935',
                            customdata=[[w, '🌙 평일 야간'] for w in sorted_for_h_bar['worker_name']]
                        ),
                        go.Bar(
                            name='🏖️ 주말 작업 (야간포함)',
                            y=sorted_for_h_bar['worker_name'],
                            x=sorted_for_h_bar['weekend_tasks'],
                            orientation='h',
                            marker_color='#FFD600',
                            customdata=[[w, '🏖️ 주말 작업'] for w in sorted_for_h_bar['worker_name']]
                        )
                    ])
                    fig_night.update_layout(
                        barmode='stack',
                        title=f"팀원별 평일 주간 vs 평일 야간 vs 주말 작업 건수 ({selected_view})",
                        height=chart_height,
                        margin=dict(l=100, r=40, t=50, b=30),
                        yaxis=dict(tickfont=dict(size=12, family="Malgun Gothic, Arial")),
                        xaxis_title="작업 건수(건)"
                    )
                    event_right = st.plotly_chart(fig_night, use_container_width=True, on_select="rerun", selection_mode=["points"], key="chart_worker_right_h")
            else:
                with col_t1_left:
                    fig_worker = px.bar(
                        display_summary,
                        x="worker_name",
                        y="total_hours",
                        color="total_hours",
                        color_continuous_scale="Blues",
                        text="total_hours",
                        labels={"worker_name": "담당자", "total_hours": "총 투입 시간(h)"},
                        title=f"팀원별 총 지원 시간(h) 순위 ({selected_view})"
                    )
                    fig_worker.update_traces(
                        texttemplate='%{text}h',
                        textposition='outside',
                        customdata=[[w] for w in display_summary['worker_name']]
                    )
                    fig_worker.update_layout(
                        height=450,
                        xaxis=dict(tickangle=-90, tickfont=dict(size=11, family="Malgun Gothic, Arial"), dtick=1)
                    )
                    event_left = st.plotly_chart(fig_worker, use_container_width=True, on_select="rerun", selection_mode=["points"], key="chart_worker_left_v")

                with col_t1_right:
                    fig_night = go.Figure(data=[
                        go.Bar(
                            name='☀️ 평일 주간',
                            x=display_summary['worker_name'],
                            y=display_summary.get('weekday_day_tasks', display_summary['total_tasks'] - display_summary['night_tasks'] - display_summary['weekend_tasks']),
                            marker_color='#42A5F5',
                            customdata=[[w, '☀️ 평일 주간'] for w in display_summary['worker_name']]
                        ),
                        go.Bar(
                            name='🌙 평일 야간 (19시~08시)',
                            x=display_summary['worker_name'],
                            y=display_summary.get('weekday_night_tasks', display_summary['night_tasks']),
                            marker_color='#E53935',
                            customdata=[[w, '🌙 평일 야간'] for w in display_summary['worker_name']]
                        ),
                        go.Bar(
                            name='🏖️ 주말 작업 (야간포함)',
                            x=display_summary['worker_name'],
                            y=display_summary['weekend_tasks'],
                            marker_color='#FFD600',
                            customdata=[[w, '🏖️ 주말 작업'] for w in display_summary['worker_name']]
                        )
                    ])
                    fig_night.update_layout(
                        barmode='stack',
                        title=f"팀원별 평일 주간 vs 평일 야간 vs 주말 작업 건수 ({selected_view})",
                        height=450,
                        xaxis=dict(tickangle=-90, tickfont=dict(size=11, family="Malgun Gothic, Arial"), dtick=1),
                        yaxis_title="작업 건수(건)"
                    )
                    event_right = st.plotly_chart(fig_night, use_container_width=True, on_select="rerun", selection_mode=["points"], key="chart_worker_right_v")

            # 🌟 [차트 클릭 인터랙션 핸들링]
            # 1. 왼쪽 그래프 클릭 시: 해당 담당자 전체 작업 내역 팝업
            if event_left and hasattr(event_left, "selection") and event_left.selection.points:
                pt_l = event_left.selection.points[0]
                target_w = None
                if "customdata" in pt_l and pt_l["customdata"]:
                    cdata = pt_l["customdata"]
                    target_w = cdata[0] if isinstance(cdata, (list, tuple)) else cdata
                elif "y" in pt_l and "가로형" in chart_orientation:
                    target_w = pt_l["y"]
                elif "x" in pt_l:
                    target_w = pt_l["x"]
                if target_w:
                    show_worker_all_tasks_dialog(target_w, df)

            # 2. 오른쪽 그래프 클릭 시: 해당 담당자의 평일 주간 / 평일 야간 / 주말 작업별 세부 내역 팝업
            if event_right and hasattr(event_right, "selection") and event_right.selection.points:
                pt_r = event_right.selection.points[0]
                target_w = None
                target_cat = "☀️ 평일 주간"
                
                if "customdata" in pt_r and pt_r["customdata"]:
                    cdata = pt_r["customdata"]
                    if isinstance(cdata, (list, tuple)) and len(cdata) >= 2:
                        target_w, target_cat = cdata[0], cdata[1]
                    elif isinstance(cdata, (list, tuple)):
                        target_w = cdata[0]
                    else:
                        target_w = cdata
                if not target_w:
                    target_w = pt_r.get("y") if "가로형" in chart_orientation else pt_r.get("x")
                
                curve_no = pt_r.get("curve_number", 0)
                if curve_no == 1:
                    target_cat = "🌙 평일 야간"
                elif curve_no == 2:
                    target_cat = "🏖️ 주말 작업"
                elif curve_no == 0:
                    target_cat = "☀️ 평일 주간"

                if target_w:
                    show_worker_category_tasks_dialog(target_w, target_cat, df)

            st.markdown("##### 📊 팀원별 종합 통계 현황판")
            st.dataframe(
                worker_summary.rename(columns={
                    "worker_name": "담당자",
                    "total_hours": "총 투입시간(h)",
                    "total_tasks": "작업 건수",
                    "night_tasks": "야간 작업 건수",
                    "weekend_tasks": "주말 작업 건수",
                    "avg_hours": "건당 평균시간(h)",
                    "company": "회사",
                    "team": "소속팀",
                    "title": "직급"
                }),
                use_container_width=True,
                hide_index=True
            )

            # ----------------------------------------------------
            # 📆 선택 월 주차(Week)별 팀원 투입 현황 & 과중 업무 모니터링 (사용자 요청 반영!)
            # ----------------------------------------------------
            st.markdown("---")
            st.markdown('<div id="weekly-monitor-section" style="scroll-margin-top: 60px;"></div>', unsafe_allow_html=True)
            st.markdown(f"##### 📆 {month_desc} - 주차(Week)별 팀원 투입 시간 현황 & 휴식 조율 모니터링")
            st.caption("선택된 월의 **각 주차별 투입 시간(h)**을 한눈에 비교하여, 한 주에 너무 많이 일한 팀원을 파악하고 다음 주 휴식을 조율할 수 있습니다.")

            if not df.empty and "week_label" in df.columns:
                pivot_df = df.pivot_table(
                    index=["worker_name", "worker_team"],
                    columns="week_label",
                    values="actual_hours",
                    aggfunc="sum",
                    fill_value=0.0
                ).round(1)

                if not pivot_df.empty:
                    week_cols = sorted(list(pivot_df.columns))

                    # 주간 최고(h) 및 기간 총시간(h) 계산
                    pivot_df["주간 최고(h)"] = pivot_df[week_cols].max(axis=1).round(1)
                    pivot_df["기간 총시간(h)"] = pivot_df[week_cols].sum(axis=1).round(1)

                    # 정렬 및 인덱스를 컬럼으로 리셋
                    pivot_df = pivot_df.sort_values(by="기간 총시간(h)", ascending=False).reset_index()
                    pivot_df = pivot_df.rename(columns={
                        "worker_name": "담당자",
                        "worker_team": "소속팀"
                    })

                    # 보상 휴가 지급 내역 전수 로드
                    all_rewards = RewardLeaveService.get_all_reward_leaves()

                    def check_overwork(row):
                        w_name = row["담당자"]
                        danger_52_weeks = []   # 52시간 이상 (빨간색)
                        caution_40_weeks = []  # 40시간 이상 ~ 52시간 미만 (주황색)
                        rewarded_weeks = []    # 보상 완료 (녹색)

                        for c in week_cols:
                            val = row[c]
                            if val >= 40.0:
                                short_w = c.split(" ")[-2] if " " in c else c
                                is_rewarded = (w_name, c) in all_rewards
                                if is_rewarded:
                                    rewarded_weeks.append(f"{short_w}({val}h:보상완료)")
                                elif val >= 52.0:
                                    danger_52_weeks.append(f"{short_w}({val}h)")
                                else:
                                    caution_40_weeks.append(f"{short_w}({val}h)")

                        if danger_52_weeks:
                            # 52시간 초과 1건이라도 있으면 빨간색 경고
                            all_unrewarded = danger_52_weeks + caution_40_weeks
                            return "🚨 " + ", ".join(all_unrewarded)
                        elif caution_40_weeks:
                            # 40~52시간 초과인 경우 주황색 경고
                            return "⚠️ " + ", ".join(caution_40_weeks)
                        elif rewarded_weeks:
                            # 모든 초과근무에 보상이 완료된 경우 녹색
                            return "✅ " + ", ".join(rewarded_weeks)
                        return "정상"

                    pivot_df["🚨 과중업무 / 보상현황"] = pivot_df.apply(check_overwork, axis=1)

                    # 컬럼 순서 변경: [담당자, 소속팀, 🚨 과중업무 / 보상현황, 주차별 컬럼들..., 주간 최고(h), 기간 총시간(h)]
                    ordered_cols = ["담당자", "소속팀", "🚨 과중업무 / 보상현황"] + week_cols + ["주간 최고(h)", "기간 총시간(h)"]
                    pivot_df = pivot_df[[c for c in ordered_cols if c in pivot_df.columns]]

                    # 과중 업무 요약 알림 (52h 초과: 빨간색, 40h~52h: 주황색)
                    danger_52_cnt = len(pivot_df[pivot_df["🚨 과중업무 / 보상현황"].str.startswith("🚨")])
                    caution_40_cnt = len(pivot_df[pivot_df["🚨 과중업무 / 보상현황"].str.startswith("⚠️")])
                    rewarded_cnt = len(pivot_df[pivot_df["🚨 과중업무 / 보상현황"].str.startswith("✅")])

                    if danger_52_cnt > 0 or caution_40_cnt > 0:
                        msg_parts = []
                        if danger_52_cnt > 0:
                            msg_parts.append(f"🚨 **주 52시간 초과 위험 {danger_52_cnt}명 (빨간색)**")
                        if caution_40_cnt > 0:
                            msg_parts.append(f"⚠️ **주 40시간 초과 주의 {caution_40_cnt}명 (주황색)**")
                        st.warning(f"{' / '.join(msg_parts)}이 감지되었습니다. (보상 완료: {rewarded_cnt}명) 숫자를 클릭하여 보상 휴가를 등록하시면 **녹색**으로 바뀝니다.")
                    elif rewarded_cnt > 0:
                        st.success(f"🎉 모든 초과 근무자({rewarded_cnt}명)에게 **보상 휴가가 100% 정상 부여 완료**되었습니다! (녹색 전환)")
                    else:
                        st.info("💡 선택된 기간 동안 주 40시간을 초과한 과중 근무자가 없습니다.")

                    # 스타일링: 52h 초과=빨간색(#D32F2F), 40h~52h=주황색(#EF6C00), 보상완료=녹색(#2E7D32)
                    def style_overwork_badge(val):
                        if isinstance(val, str):
                            if "🚨" in val:
                                return "background-color: #D32F2F; color: #FFFFFF; font-weight: 900; text-align: center;"
                            elif "⚠️" in val:
                                return "background-color: #EF6C00; color: #FFFFFF; font-weight: 900; text-align: center;"
                            elif "✅" in val:
                                return "background-color: #2E7D32; color: #FFFFFF; font-weight: 900; text-align: center;"
                        return "color: #4CAF50; font-weight: 600; text-align: center;"

                    numeric_cols = [c for c in week_cols + ["주간 최고(h)", "기간 총시간(h)"] if c in pivot_df.columns]

                    def highlight_row_cells(row):
                        styles = [''] * len(row)
                        w_name = row["담당자"]
                        for i, col in enumerate(row.index):
                            if col in week_cols:
                                val = row[col]
                                if isinstance(val, (int, float)) and val >= 40.0:
                                    is_rewarded = (w_name, col) in all_rewards
                                    if is_rewarded:
                                        styles[i] = "background-color: #C8E6C9; color: #1B5E20; font-weight: bold;"
                                    elif val >= 52.0:
                                        # 52시간 이상 ➔ 빨간색
                                        styles[i] = "background-color: #FFCDD2; color: #B71C1C; font-weight: bold;"
                                    else:
                                        # 40시간 이상 52시간 미만 ➔ 주황색
                                        styles[i] = "background-color: #FFE0B2; color: #E65100; font-weight: bold;"
                        return styles

                    styled_pivot = pivot_df.style.format(
                        "{:.1f}", subset=numeric_cols
                    ).map(
                        style_overwork_badge,
                        subset=["🚨 과중업무 / 보상현황"]
                    ).apply(
                        highlight_row_cells,
                        axis=1
                    )

                    column_configs = {
                        "담당자": st.column_config.TextColumn("담당자", width="small"),
                        "소속팀": st.column_config.TextColumn("소속팀", width="small"),
                        "🚨 과중업무 / 보상현황": st.column_config.TextColumn("🚨 과중업무 / 보상현황", width="medium"),
                    }
                    for num_col in numeric_cols:
                        column_configs[num_col] = st.column_config.NumberColumn(num_col, format="%.1f", width="small")

                    # 1. 주차별 매트릭스 표 렌더링 (특정 셀/숫자 클릭 시 해당 주차 팝업 즉시 연동)
                    st.caption("💡 표에서 **원하는 숫자(예: 99.0)나 셀을 클릭**하시면, 해당 인원의 **그 주차 세부 작업 내역 팝업(새창)**이 즉시 열립니다.")
                    selected_table = st.dataframe(
                        styled_pivot,
                        column_config=column_configs,
                        use_container_width=True,
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-cell",
                        key="weekly_matrix_selector"
                    )

                    # 2. 셀/숫자 클릭 감지 시 모달 팝업 자동 실행 (1회성 클릭 이벤트만 감지하여 사이드바 조작 시 오작동 방지)
                    target_w_name = None
                    target_col_name = None

                    sel_obj = None
                    if selected_table and hasattr(selected_table, "selection"):
                        sel_obj = selected_table.selection
                    elif selected_table and isinstance(selected_table, dict):
                        sel_obj = selected_table.get("selection")

                    if sel_obj:
                        # 1) cells 필드 검사 (tuple list: [(row, col), ...])
                        cells = getattr(sel_obj, "cells", None) if hasattr(sel_obj, "cells") else (sel_obj.get("cells") if isinstance(sel_obj, dict) else None)
                        if cells and len(cells) > 0:
                            first_cell = cells[0]
                            if isinstance(first_cell, (tuple, list)) and len(first_cell) >= 2:
                                r_idx, c_name = first_cell[0], first_cell[1]
                                if r_idx is not None and r_idx < len(pivot_df):
                                    target_w_name = pivot_df.iloc[r_idx]["담당자"]
                                    target_col_name = c_name
                            elif isinstance(first_cell, dict):
                                r_idx = first_cell.get("row")
                                c_name = first_cell.get("column")
                                if r_idx is not None and r_idx < len(pivot_df):
                                    target_w_name = pivot_df.iloc[r_idx]["담당자"]
                                    target_col_name = c_name

                        # 2) rows & columns 필드 검사
                        if not target_w_name:
                            rows = getattr(sel_obj, "rows", None) if hasattr(sel_obj, "rows") else (sel_obj.get("rows") if isinstance(sel_obj, dict) else None)
                            cols = getattr(sel_obj, "columns", None) if hasattr(sel_obj, "columns") else (sel_obj.get("columns") if isinstance(sel_obj, dict) else None)
                            
                            if rows and len(rows) > 0:
                                r_idx = rows[0]
                                if r_idx < len(pivot_df):
                                    target_w_name = pivot_df.iloc[r_idx]["담당자"]
                                    
                            if cols and len(cols) > 0:
                                target_col_name = cols[0]

                    # 3. 새로운 셀 클릭 시에만 팝업 실행 (사이드바 조작 시에는 팝업 방지)
                    current_click_token = f"{target_w_name}_{target_col_name}" if target_w_name else None
                    last_click_token = st.session_state.get("_last_matrix_click_token")

                    if current_click_token and current_click_token != last_click_token:
                        st.session_state["_last_matrix_click_token"] = current_click_token
                        show_weekly_detail_dialog(target_w_name, df, default_week_name=target_col_name)
                    elif not current_click_token:
                        st.session_state["_last_matrix_click_token"] = None

    # ------------------------------------------
    # TAB 2: 팀별 업무량 비교
    # ------------------------------------------
    with tab2:
        st.subheader("🏢 팀별(기술 1/2/3팀 + PI팀) 총 투입 시간 및 공수 비교")
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
        team_summary = team_summary.sort_values(by="total_hours", ascending=False)
        
        col_t2_1, col_t2_2 = st.columns(2)
        with col_t2_1:
            fig_team_bar = px.bar(
                team_summary,
                x="worker_team",
                y="total_hours",
                color="worker_team",
                text="total_hours",
                labels={"worker_team": "팀", "total_hours": "총 지원 시간(h)"},
                title="팀별 총 지원 시간(h) 비교"
            )
            fig_team_bar.update_traces(texttemplate='%{text}h', textposition='outside')
            fig_team_bar.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig_team_bar, use_container_width=True)

        with col_t2_2:
            fig_team_avg = px.bar(
                team_summary,
                x="worker_team",
                y="avg_hours_per_person",
                color="worker_team",
                text="avg_hours_per_person",
                labels={"worker_team": "팀", "avg_hours_per_person": "1인당 평균 시간(h)"},
                title="팀별 1인당 평균 지원 시간(h) 비교"
            )
            fig_team_avg.update_traces(texttemplate='%{text}h', textposition='outside')
            fig_team_avg.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig_team_avg, use_container_width=True)

        st.markdown("##### 📋 팀별 상세 집계 표")
        st.dataframe(
            team_summary.rename(columns={
                "worker_team": "소속팀",
                "total_hours": "총 투입시간(h)",
                "total_tasks": "작업 건수",
                "night_tasks": "야간 작업 건수",
                "worker_count": "투입 인원(명)",
                "avg_hours_per_person": "1인당 평균시간(h)"
            }),
            use_container_width=True,
            hide_index=True
        )

    # ------------------------------------------
    # TAB 3: 월별 / 주별 / 일별 추이 분석
    # ------------------------------------------
    with tab3:
        st.subheader("📈 월별 / 주별 / 일별 지원 시간 추이 및 시계열 분석")
        monthly_trend = StatsService.get_monthly_trend(df)
        
        if not df.empty:
            col_t3_1, col_t3_2 = st.columns(2)
            with col_t3_1:
                if not monthly_trend.empty:
                    fig_monthly = px.line(
                        monthly_trend,
                        x="month_str",
                        y="total_hours",
                        markers=True,
                        labels={"month_str": "월", "total_hours": "총 지원 시간(h)"},
                        title="월별 총 지원 시간(h) 변동 추이"
                    )
                    fig_monthly.update_traces(line_color="#1E88E5", line_width=3)
                    fig_monthly.update_layout(height=350)
                    st.plotly_chart(fig_monthly, use_container_width=True)
                
            with col_t3_2:
                # 주별 추이 차트 (신규 추가!)
                weekly_df = df.groupby("week_label")["actual_hours"].sum().reset_index()
                if not weekly_df.empty:
                    fig_weekly = px.bar(
                        weekly_df,
                        x="week_label",
                        y="actual_hours",
                        text="actual_hours",
                        labels={"week_label": "주차(Week)", "actual_hours": "총 투입 시간(h)"},
                        title="주차(Week)별 총 지원 시간 분포"
                    )
                    fig_weekly.update_traces(texttemplate='%{text}h', textposition='outside', marker_color='#42A5F5')
                    fig_weekly.update_layout(height=350, xaxis=dict(tickangle=-30))
                    st.plotly_chart(fig_weekly, use_container_width=True)

            st.markdown("##### 📅 일자별 작업 시간 분포")
            daily_df = df.groupby("date_str")["actual_hours"].sum().reset_index()
            fig_daily = px.bar(
                daily_df,
                x="date_str",
                y="actual_hours",
                labels={"date_str": "일자", "actual_hours": "작업 시간(h)"},
                title="일자별 작업 시간 분포"
            )
            fig_daily.update_layout(height=320)
            st.plotly_chart(fig_daily, use_container_width=True)

    # ------------------------------------------
    # TAB 4: 고객사별 공수 분포
    # ------------------------------------------
    with tab4:
        st.subheader("🏢 고객사별 지원 시간 및 공수 비중")
        client_summary = StatsService.get_client_summary(df)
        
        if not client_summary.empty:
            col_t4_1, col_t4_2 = st.columns([1, 1])
            with col_t4_1:
                fig_client_pie = px.pie(
                    client_summary,
                    names="client_name",
                    values="total_hours",
                    hole=0.45,
                    title="고객사별 투입 공수(시간) 점유율",
                    labels={"client_name": "고객사", "total_hours": "시간"}
                )
                fig_client_pie.update_traces(textposition='inside', textinfo='percent+label')
                fig_client_pie.update_layout(height=400)
                st.plotly_chart(fig_client_pie, use_container_width=True)

            with col_t4_2:
                fig_client_bar = px.bar(
                    client_summary,
                    x="total_hours",
                    y="client_name",
                    orientation='h',
                    labels={"total_hours": "총 투입시간(h)", "client_name": "고객사"},
                    title="고객사별 투입 시간(h) 순위",
                    color="total_hours",
                    color_continuous_scale="Viridis"
                )
                fig_client_bar.update_layout(height=400, yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_client_bar, use_container_width=True)

    # ------------------------------------------
    # TAB 5: 예정 vs 실제 소요시간 분석
    # ------------------------------------------
    with tab5:
        st.subheader("⏱️ 예정 소요시간 대비 실제 시간 편차 분석")
        completed_df = df[df["status"] == "COMPLETED"].copy()
        
        if not completed_df.empty:
            completed_df["diff_minutes"] = completed_df["actual_minutes"] - completed_df["estimated_minutes"]
            completed_df["diff_hours"] = (completed_df["diff_minutes"] / 60.0).round(1)
            completed_df["overdue_status"] = completed_df["diff_minutes"].apply(
                lambda x: "초과 소요" if x > 0 else ("단축 완료" if x < 0 else "정시 완료")
            )
            
            col_t5_1, col_t5_2 = st.columns([3, 2])
            with col_t5_1:
                fig_scatter = px.scatter(
                    completed_df,
                    x="estimated_hours",
                    y="actual_hours",
                    color="overdue_status",
                    hover_data=["worker_name", "client_name", "task_description"],
                    color_discrete_map={"초과 소요": "#E53935", "단축 완료": "#43A047", "정시 완료": "#1E88E5"},
                    labels={"estimated_hours": "예정 시간(h)", "actual_hours": "실제 완료 시간(h)"},
                    title="예정 시간 vs 실제 완료 시간 비교 산점도"
                )
                max_val = max(completed_df["estimated_hours"].max(), completed_df["actual_hours"].max()) + 1
                fig_scatter.add_trace(go.Scatter(
                    x=[0, max_val], y=[0, max_val],
                    mode='lines',
                    line=dict(dash='dash', color='gray'),
                    name='예정=실제 기준선'
                ))
                fig_scatter.update_layout(height=380)
                st.plotly_chart(fig_scatter, use_container_width=True)

            with col_t5_2:
                type_summary = StatsService.get_type_summary(df)
                fig_type = px.bar(
                    type_summary,
                    x="log_type",
                    y="total_hours",
                    color="log_type",
                    labels={"log_type": "작업 구분", "total_hours": "시간(h)"},
                    title="작업 유형별(정기점검, OS업그레이드 등) 투입 시간"
                )
                fig_type.update_layout(height=380, showlegend=False)
                st.plotly_chart(fig_type, use_container_width=True)


if __name__ == "__main__":
    main()
