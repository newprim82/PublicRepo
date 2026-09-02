import io
import time
import warnings
warnings.filterwarnings("ignore")

import calendar
import importlib
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone

KST_TIMEZONE = timezone(timedelta(hours=9))

def get_current_kst_time() -> datetime:
    """한국 표준시(KST, UTC+9) 현재 시각 반환"""
    return datetime.now(KST_TIMEZONE)

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

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


from src.services.team_service import TeamService, DEFAULT_TEAMS, UNASSIGNED_TEAM

def get_all_teams_safe() -> list:
    """Streamlit Cloud 핫 리로드 시 모듈 캐시 불일치를 100% 방어하는 안전한 팀 목록 반환 함수"""
    try:
        if hasattr(TeamService, "get_all_teams"):
            return TeamService.get_all_teams()
        if hasattr(team_service, "get_all_teams"):
            return team_service.get_all_teams()
    except Exception:
        pass
    return ["기술본부", "기술 1팀", "기술 2팀", "기술 3팀", "PI팀"]
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
    /* 🌟 글래스모피즘 타이틀 박스 */
    .dashboard-title-box {
        background: linear-gradient(90deg, rgba(30, 41, 59, 0.5) 0%, rgba(15, 23, 42, 0.7) 100%);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 12px 18px;
        margin-bottom: 14px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    }
    .main-title-text {
        font-size: 23px;
        font-weight: 900;
        color: #FFFFFF;
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
        letter-spacing: -0.3px;
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
    
    /* 💊 Linear / Apple 스타일 프리미엄 캡슐(Pill) 탭 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: rgba(15, 23, 42, 0.7);
        padding: 5px 6px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        margin-bottom: 16px;
        box-shadow: inset 0 2px 6px rgba(0, 0, 0, 0.4);
    }
    .stTabs [data-baseweb="tab"] {
        height: 38px;
        white-space: nowrap;
        background: transparent;
        color: #94A3B8;
        border-radius: 8px;
        padding: 6px 14px;
        border: none !important;
        font-size: 13.5px;
        font-weight: 600;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(255, 255, 255, 0.06);
        color: #F8FAFC;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
        color: #FFFFFF !important;
        font-weight: 700;
        box-shadow: 0 2px 10px rgba(37, 99, 235, 0.4) !important;
        border-radius: 8px !important;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }
    .stTabs [data-baseweb="tab-border"] {
        display: none !important;
    }
    
    /* 🌟 글래스모피즘 프리미엄 네온 KPI 카드 스타일 */
    .kpi-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.09);
        border-radius: 14px;
        padding: 16px 18px;
        margin-bottom: 12px;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.35);
        transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.25s ease, border-color 0.25s ease;
    }
    .kpi-card:hover {
        transform: translateY(-4px);
        border-color: rgba(56, 189, 248, 0.5);
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.5), 0 0 16px rgba(56, 189, 248, 0.2);
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
        font-size: 30px;
        font-weight: 900;
        line-height: 1.1;
        margin-bottom: 8px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    .kpi-unit {
        font-size: 15px;
        font-weight: 600;
        color: #64748B;
        margin-left: 4px;
    }
    .kpi-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 3px 9px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: -0.2px;
    }
    .badge-cyan { background: rgba(0, 229, 255, 0.12); color: #00E5FF; border: 1px solid rgba(0, 229, 255, 0.25); }
    .badge-green { background: rgba(0, 230, 118, 0.12); color: #00E676; border: 1px solid rgba(0, 230, 118, 0.25); }
    .badge-purple { background: rgba(179, 136, 255, 0.12); color: #B388FF; border: 1px solid rgba(179, 136, 255, 0.25); }
    .badge-amber { background: rgba(255, 171, 0, 0.12); color: #FFAB00; border: 1px solid rgba(255, 171, 0, 0.25); }
    .badge-red { background: rgba(255, 82, 82, 0.12); color: #FF5252; border: 1px solid rgba(255, 82, 82, 0.25); }

    @keyframes pulse-green {
        0% { box-shadow: 0 0 0 0 rgba(0, 230, 118, 0.7); }
        70% { box-shadow: 0 0 0 8px rgba(0, 230, 118, 0); }
        100% { box-shadow: 0 0 0 0 rgba(0, 230, 118, 0); }
    }
    .live-pulse-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(0, 230, 118, 0.15);
        color: #00E676;
        border: 1px solid #00E676;
        border-radius: 12px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 700;
        animation: pulse-green 2s infinite;
    }
    
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


@st.cache_data(ttl=15, show_spinner=False)
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


def clear_all_web_caches():
    """DB 데이터는 절대 건드리지 않고, Streamlit 웹 메모리 캐시만 깨끗하게 초기화"""
    st.cache_data.clear()
    st.cache_resource.clear()
    for key in list(st.session_state.keys()):
        if key not in ["selected_menu"]:
            del st.session_state[key]


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


def render_today_live_board(df_raw: pd.DataFrame, team_mappings: dict, selected_team: str = "전체 팀"):
    """[🟢 오늘 실시간 작업 현황 (Today Live Board)] 실시간 관제 대시보드 컴포넌트"""
    kst_now = get_current_kst_time()
    today_date = kst_now.date()
    kst_now_naive = kst_now.replace(tzinfo=None)

    # 1. 오늘 날짜 데이터 필터링
    if df_raw.empty or "start_time" not in df_raw.columns:
        st.info("현재 등록된 작업 로그 데이터가 없습니다.")
        return

    today_df = df_raw[df_raw["start_time"].dt.date == today_date].copy()

    # 팀 필터링 적용
    if selected_team != "전체 팀":
        today_df = today_df[today_df["worker_team"] == selected_team]

    # 2. 진행 중(PENDING) vs 오늘 완료(COMPLETED) 분리
    pend_df = today_df[today_df["status"] == "PENDING"].sort_values("start_time", ascending=False)
    comp_df = today_df[today_df["status"] == "COMPLETED"].sort_values("start_time", ascending=False)

    tot_workers = today_df["worker_name"].nunique() if not today_df.empty else 0
    tot_hours = round(comp_df["actual_hours"].sum() + pend_df["estimated_hours"].sum(), 1) if not today_df.empty else 0.0

    # 3. 상단 실시간 요약 바 (Live Status Summary)
    summary_html = f"""<div style="background: linear-gradient(90deg, #0F172A 0%, #1E293B 100%); border: 1px solid rgba(0, 230, 118, 0.4); border-radius: 12px; padding: 14px 20px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; box-shadow: 0 4px 14px rgba(0,0,0,0.3);"><div style="display: flex; align-items: center; gap: 10px;"><span style="background: rgba(0, 230, 118, 0.15); color: #00E676; border: 1px solid #00E676; border-radius: 12px; padding: 3px 10px; font-size: 11px; font-weight: 700;">● LIVE 관제 중</span><span style="font-size: 16px; font-weight: 700; color: #FFFFFF;">오늘 ({today_date.strftime('%Y년 %m월 %d일')}) 실시간 현장 지원 현황</span><span style="font-size: 12px; color: #94A3B8; background: rgba(255,255,255,0.08); padding: 3px 8px; border-radius: 6px;">선택: {selected_team}</span></div><div style="display: flex; align-items: center; gap: 18px; font-size: 13.5px; font-weight: 600;"><span style="color: #E2E8F0;">👥 오늘 투입: <b style="color: #38BDF8;">{tot_workers}명</b></span><span style="color: #E2E8F0;">⏳ 진행 중: <b style="color: #00E676;">{len(pend_df)}건</b></span><span style="color: #E2E8F0;">✅ 완료: <b style="color: #818CF8;">{len(comp_df)}건</b></span><span style="color: #E2E8F0;">⏱️ 총 지원 공수: <b style="color: #FBBF24;">{tot_hours}시간</b></span></div></div>"""
    st.markdown(summary_html, unsafe_allow_html=True)

    if today_df.empty:
        st.info(f"☕ 오늘({today_date.strftime('%Y-%m-%d')}) [{selected_team}]에 등록된 실시간 작업 보고가 아직 없습니다. 카카오톡에 시작 보고가 올라오면 10분 내로 여기에 실시간으로 표시됩니다!")
        return

    # 4. 실시간 진행 중(PENDING) 작업 섹션 (팀 단위 그룹 렌더링)
    st.markdown(f"#### ⏳ 실시간 진행 중인 작업 (`{len(pend_df)}건`)")
    if pend_df.empty:
        st.success("🎉 현재 진행 중인 미완료 작업이 없습니다. 오늘 모든 작업이 성공적으로 완료되었습니다!")
    else:
        all_teams_order = get_all_teams_safe() + [UNASSIGNED_TEAM]
        active_teams = [t for t in all_teams_order if t in pend_df["worker_team"].values]
        for extra_t in pend_df["worker_team"].unique():
            if extra_t not in active_teams:
                active_teams.append(extra_t)

        for t_name in active_teams:
            t_pend = pend_df[pend_df["worker_team"] == t_name]
            if t_pend.empty:
                continue

            # 웅장하고 눈에 확 띄는 프리미엄 팀 섹션 헤더 배너 (팀명 바로 옆에 건수 배지 배치)
            st.markdown(f"""<div style="margin-top: 22px; margin-bottom: 12px; background: linear-gradient(90deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.6) 100%); border-left: 6px solid #00E5FF; border-radius: 8px; padding: 10px 18px; display: flex; align-items: center; gap: 14px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);"><span style="font-size: 20px; font-weight: 900; color: #FFFFFF; letter-spacing: -0.3px;">🏢 {t_name}</span><span style="background: rgba(0, 230, 118, 0.2); color: #00E676; border: 1.5px solid #00E676; padding: 3px 12px; border-radius: 20px; font-size: 12px; font-weight: 800; box-shadow: 0 0 10px rgba(0, 230, 118, 0.25);">🟢 {len(t_pend)}건 진행 중</span></div>""", unsafe_allow_html=True)

            p_cols = st.columns(3)
            for idx, (_, r) in enumerate(t_pend.iterrows()):
                with p_cols[idx % 3]:
                    w_name = r["worker_name"]
                    w_title = r["worker_title"] or ""
                    c_name = r["client_name"]
                    t_desc = r["task_description"]
                    st_dt = r["start_time"]

                    # KST 기준 경과 시간 계산
                    st_dt_naive = st_dt.replace(tzinfo=None) if hasattr(st_dt, 'tzinfo') and st_dt.tzinfo else st_dt
                    diff_sec = max(0, int((kst_now_naive - st_dt_naive).total_seconds())) if pd.notna(st_dt) else 0
                    elapsed_mins = diff_sec // 60
                    elapsed_hours = round(elapsed_mins / 60, 1)
                    est_hours = float(r.get("estimated_hours") or 0)
                    is_overtime = elapsed_hours > est_hours and est_hours > 0

                    raw_pct = int((elapsed_hours / est_hours) * 100) if est_hours > 0 else (100 if elapsed_hours > 0 else 50)
                    bar_width_pct = min(100, max(5, raw_pct))

                    if is_overtime:
                        bar_bg = "linear-gradient(90deg, rgba(244, 63, 94, 0.45) 0%, rgba(225, 29, 72, 0.35) 100%)"
                        bar_border = "1px solid rgba(244, 63, 94, 0.4)"
                        pct_text_color = "#FFA4B2"
                        pct_display = f"{raw_pct}% (초과)"
                    else:
                        bar_bg = "linear-gradient(90deg, rgba(14, 165, 233, 0.5) 0%, rgba(56, 189, 248, 0.3) 100%)"
                        bar_border = "1px solid rgba(56, 189, 248, 0.35)"
                        pct_text_color = "#38BDF8"
                        pct_display = f"{raw_pct}%"

                    time_str = st_dt.strftime("%H:%M") if pd.notna(st_dt) else "시각 미상"
                    title_badge = f"<span style='background:rgba(255,255,255,0.1); padding:2px 6px; border-radius:4px; font-size:11px; margin-left:4px;'>{w_title}</span>" if w_title else ""
                    night_badge = "<span style='background:rgba(244,63,94,0.2); color:#F43F5E; padding:2px 6px; border-radius:4px; font-size:11px; margin-left:4px;'>🌙 야간</span>" if r.get("is_night_work") else ""
                    weekend_badge = "<span style='background:rgba(245,158,11,0.2); color:#F59E0B; padding:2px 6px; border-radius:4px; font-size:11px; margin-left:4px;'>🏖️ 주말</span>" if r.get("is_weekend_work") else ""

                    border_color = "#F43F5E" if is_overtime else "#00E676"
                    card_html = f"""<div style="background: linear-gradient(135deg, rgba(15, 23, 42, 0.9) 0%, rgba(30, 41, 59, 0.8) 100%); border: 1px solid {border_color}; border-radius: 12px; padding: 12px 14px; margin-bottom: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.25);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;"><div><span style="font-size: 14.5px; font-weight: 700; color: #FFFFFF;">👤 {w_name}</span>{title_badge}{night_badge}{weekend_badge}</div><span style="background: rgba(0, 230, 118, 0.15); color: #00E676; border: 1px solid #00E676; border-radius: 10px; padding: 2px 7px; font-size: 10.5px; font-weight: 700;">⏳ 진행 중 ({time_str})</span></div><div style="font-size: 13.5px; color: #F8FAFC; font-weight: 600; margin-bottom: 5px;">🏢 <span style="color: #38BDF8;">{c_name}</span></div><div style="position: relative; overflow: hidden; background: rgba(0, 0, 0, 0.35); border-radius: 8px; border: {bar_border}; margin-bottom: 6px; min-height: 34px; display: flex; align-items: center;"><div style="position: absolute; left: 0; top: 0; bottom: 0; width: {bar_width_pct}%; background: {bar_bg}; border-radius: 7px; transition: width 0.6s ease;"></div><div style="position: relative; z-index: 2; width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 5px 10px; font-size: 12.5px; font-weight: 600; color: #FFFFFF; text-shadow: 0 1px 2px rgba(0,0,0,0.8); gap: 6px;"><span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 78%;">{t_desc}</span><span style="font-weight: 700; color: {pct_text_color}; font-size: 11.5px; white-space: nowrap; background: rgba(0,0,0,0.4); padding: 1px 5px; border-radius: 4px;">{pct_display}</span></div></div><div style="display: flex; justify-content: space-between; font-size: 11.5px; color: #94A3B8; margin-top: 2px;"><span>⏱️ 예정: <b>{est_hours}h</b></span><span style="color: {'#F43F5E; font-weight:700;' if is_overtime else '#00E676;'}">⏱️ 경과: <b>{elapsed_hours}h</b> ({elapsed_mins}분) {'⚠️ 초과' if is_overtime else ''}</span></div></div>"""
                    st.markdown(card_html, unsafe_allow_html=True)

    st.write("")
    st.divider()

    # 5. 오늘 완료된 작업(COMPLETED) 섹션 (팀 단위 그룹 렌더링)
    st.markdown(f"#### ✅ 오늘 완료된 작업 (`{len(comp_df)}건`)")
    if comp_df.empty:
        st.info("오늘 완료 보고된 작업이 아직 없습니다.")
    else:
        all_teams_order = get_all_teams_safe() + [UNASSIGNED_TEAM]
        active_comp_teams = [t for t in all_teams_order if t in comp_df["worker_team"].values]
        for extra_t in comp_df["worker_team"].unique():
            if extra_t not in active_comp_teams:
                active_comp_teams.append(extra_t)

        for t_name in active_comp_teams:
            t_comp = comp_df[comp_df["worker_team"] == t_name]
            if t_comp.empty:
                continue

            # 웅장하고 눈에 확 띄는 프리미엄 완료 팀 섹션 헤더 배너 (팀명 바로 옆에 건수 배지 배치)
            st.markdown(f"""<div style="margin-top: 20px; margin-bottom: 10px; background: linear-gradient(90deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.5) 100%); border-left: 6px solid #818CF8; border-radius: 8px; padding: 9px 18px; display: flex; align-items: center; gap: 14px; box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);"><span style="font-size: 19px; font-weight: 900; color: #FFFFFF; letter-spacing: -0.3px;">🏢 {t_name}</span><span style="background: rgba(129, 140, 248, 0.2); color: #818CF8; border: 1.5px solid #818CF8; padding: 2px 10px; border-radius: 20px; font-size: 11.5px; font-weight: 800;">✅ {len(t_comp)}건 완료</span></div>""", unsafe_allow_html=True)

            c_cols = st.columns(3)
            for idx, (_, r) in enumerate(t_comp.iterrows()):
                with c_cols[idx % 3]:
                    w_name = r["worker_name"]
                    w_title = r["worker_title"] or ""
                    c_name = r["client_name"]
                    t_desc = r["task_description"]
                    st_dt = r["start_time"]
                    ed_dt = r["end_time"]
                    act_h = r["actual_hours"]

                    st_str = st_dt.strftime("%H:%M") if pd.notna(st_dt) else "?"
                    ed_str = ed_dt.strftime("%H:%M") if pd.notna(ed_dt) else "완료"

                    title_badge = f"<span style='background:rgba(255,255,255,0.08); padding:2px 6px; border-radius:4px; font-size:11px; margin-left:4px;'>{w_title}</span>" if w_title else ""

                    comp_html = f"""<div style="background: linear-gradient(135deg, rgba(15, 23, 42, 0.6) 0%, rgba(30, 41, 59, 0.5) 100%); border: 1px solid rgba(129, 140, 248, 0.25); border-radius: 10px; padding: 10px 12px; margin-bottom: 8px;"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;"><div><span style="font-size: 13.5px; font-weight: 700; color: #E2E8F0;">👤 {w_name}</span>{title_badge}</div><span style="background: rgba(129, 140, 248, 0.15); color: #818CF8; border: 1px solid rgba(129, 140, 248, 0.4); border-radius: 10px; padding: 2px 7px; font-size: 10.5px; font-weight: 700;">✅ {st_str}~{ed_str} ({act_h}h)</span></div><div style="font-size: 13px; color: #F1F5F9; font-weight: 600; margin-bottom: 3px;">🏢 <span style="color: #38BDF8;">{c_name}</span></div><div style="font-size: 12px; color: #94A3B8; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{t_desc}</div></div>"""
                    st.markdown(comp_html, unsafe_allow_html=True)


def render_calendar_and_heatmap_tab(df: pd.DataFrame, df_raw: pd.DataFrame, selected_team: str = "전체 팀"):
    """[📅 작업 캘린더 & 밀도 히트맵] 탭 렌더링 컴포넌트"""
    if df.empty or "start_time" not in df.columns:
        st.info("표시할 작업 데이터가 없습니다.")
        return

    st.markdown(f"### 📅 {selected_team} - 작업 밀도 히트맵 & 월간 캘린더")
    st.caption("날짜별 작업량 집중도, 인터랙티브 월간 달력 및 요일/시간대별 피크타임 골든타임 분석을 제공합니다.")

    # 대상 월 목록
    available_months = sorted(df["start_time"].dt.strftime("%Y-%m").dropna().unique(), reverse=True)
    if not available_months:
        st.info("작업 기간 데이터가 없습니다.")
        return

    col_m_sel, _ = st.columns([1.5, 2.5])
    with col_m_sel:
        pick_month = st.selectbox("📅 조회 기준 월 선택:", options=available_months, index=0, key="cal_pick_month")

    df_month = df[df["start_time"].dt.strftime("%Y-%m") == pick_month].copy()
    if df_month.empty:
        st.info(f"{pick_month}에 등록된 작업 데이터가 없습니다.")
        return

    year, month = map(int, pick_month.split("-"))

    # 1. 상단 월간 핵심 요약 카드
    tot_h = round(df_month["actual_hours"].sum(), 1)
    tot_cnt = len(df_month)
    tot_w = df_month["worker_name"].nunique()
    active_days = df_month["start_time"].dt.date.nunique()

    summary_cards_html = f"""<div style="display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap;"><div style="flex: 1; min-width: 140px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 10px; padding: 12px 16px;"><div style="font-size: 12px; color: #94A3B8;">📅 작업 일수</div><div style="font-size: 22px; font-weight: 800; color: #38BDF8;">{active_days}일 <span style="font-size: 13px; font-weight: 500; color: #64748B;">/ 월</span></div></div><div style="flex: 1; min-width: 140px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(0, 230, 118, 0.3); border-radius: 10px; padding: 12px 16px;"><div style="font-size: 12px; color: #94A3B8;">⏱️ 총 투입 공수</div><div style="font-size: 22px; font-weight: 800; color: #00E676;">{tot_h}시간</div></div><div style="flex: 1; min-width: 140px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(129, 140, 248, 0.3); border-radius: 10px; padding: 12px 16px;"><div style="font-size: 12px; color: #94A3B8;">📋 총 작업 건수</div><div style="font-size: 22px; font-weight: 800; color: #818CF8;">{tot_cnt}건</div></div><div style="flex: 1; min-width: 140px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(251, 191, 36, 0.3); border-radius: 10px; padding: 12px 16px;"><div style="font-size: 12px; color: #94A3B8;">👥 투입 인원</div><div style="font-size: 22px; font-weight: 800; color: #FBBF24;">{tot_w}명</div></div></div>"""
    st.markdown(summary_cards_html, unsafe_allow_html=True)

    # ----------------------------------------------------
    # 2. 🗓️ 인터랙티브 월간 캘린더 그리드 (Monthly Calendar)
    # ----------------------------------------------------
    st.markdown(f"#### 🗓️ {pick_month} 월간 작업 캘린더")
    st.caption("달력의 각 날짜별 총 작업 시간과 참여 인원입니다.")

    df_month["day_num"] = df_month["start_time"].dt.day
    day_summary = df_month.groupby("day_num").agg(
        total_hours=("actual_hours", "sum"),
        total_cnt=("id", "count"),
        workers=("worker_name", lambda x: list(x.unique()))
    ).to_dict("index")

    cal_matrix = calendar.monthcalendar(year, month)
    weekdays = ["월 (Mon)", "화 (Tue)", "수 (Wed)", "목 (Thu)", "금 (Fri)", "토 (Sat)", "일 (Sun)"]

    h_cols = st.columns(7)
    for idx, wd in enumerate(weekdays):
        with h_cols[idx]:
            h_color = "#F43F5E" if idx == 6 else ("#38BDF8" if idx == 5 else "#E2E8F0")
            st.markdown(f"<div style='text-align:center; font-weight:700; color:{h_color}; background:rgba(30,41,59,0.6); padding:6px; border-radius:6px; font-size:12px; margin-bottom:6px;'>{wd}</div>", unsafe_allow_html=True)

    for week in cal_matrix:
        w_cols = st.columns(7)
        for idx, day in enumerate(week):
            with w_cols[idx]:
                if day == 0:
                    st.markdown("<div style='height:76px; background:rgba(15,23,42,0.2); border-radius:8px; margin-bottom:6px;'></div>", unsafe_allow_html=True)
                else:
                    day_data = day_summary.get(day)
                    num_color = "#F43F5E" if idx == 6 else ("#38BDF8" if idx == 5 else "#F8FAFC")

                    if day_data:
                        d_hours = round(day_data["total_hours"], 1)
                        d_cnt = day_data["total_cnt"]
                        d_workers = day_data["workers"][:2]
                        w_str = ", ".join(d_workers) + (f" 외 {len(day_data['workers'])-2}명" if len(day_data["workers"]) > 2 else "")

                        bg_opacity = min(0.85, 0.25 + (d_hours / 35.0) * 0.6)
                        cell_html = f"""<div style="min-height:76px; background: rgba(16, 185, 129, {bg_opacity:.2f}); border: 1px solid rgba(16, 185, 129, 0.6); border-radius: 8px; padding: 5px 7px; margin-bottom: 6px; box-shadow: 0 2px 5px rgba(0,0,0,0.2);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;"><span style="font-weight: 800; font-size: 13px; color: {num_color};">{day}</span><span style="background: rgba(0,0,0,0.4); color: #A7F3D0; font-size: 10px; font-weight: 700; padding: 1px 4px; border-radius: 4px;">{d_cnt}건 ({d_hours}h)</span></div><div style="font-size: 10.5px; color: #FFFFFF; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">👥 {w_str}</div></div>"""
                        st.markdown(cell_html, unsafe_allow_html=True)
                    else:
                        cell_html = f"""<div style="min-height:76px; background: rgba(15, 23, 42, 0.4); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 8px; padding: 5px 7px; margin-bottom: 6px;"><div style="font-weight: 700; font-size: 12px; color: {num_color}; opacity: 0.5;">{day}</div><div style="font-size: 10px; color: #475569; margin-top: 8px; text-align: center;">-</div></div>"""
                        st.markdown(cell_html, unsafe_allow_html=True)

    st.write("")
    st.divider()

    # ----------------------------------------------------
    # 3. ⏰ 요일별 × 시간대별 피크타임 골든타임 히트맵
    # ----------------------------------------------------
    st.markdown("#### ⏰ 요일별 × 시작 시간대별 작업 집중도 (골든타임 분석)")
    st.caption("기술본부의 현장 지원이 주로 어느 요일, 몇 시에 시작되는지 한눈에 파악합니다.")

    df_peak = df.copy()
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
        color_continuous_scale="Viridis",
        aspect="auto",
        text_auto=True
    )
    fig_peak.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=20, b=20),
        height=320
    )
    st.plotly_chart(fig_peak, use_container_width=True)

    # ----------------------------------------------------
    # 4. 🔍 특정 날짜 상세 작업 목록 탐색기
    # ----------------------------------------------------
    st.divider()
    st.markdown(f"#### 🔍 {pick_month} 날짜별 상세 작업 목록 탐색기")
    
    active_day_list = sorted(df_month["day_num"].unique())
    if active_day_list:
        c_day_pick, _ = st.columns([1.5, 2.5])
        with c_day_pick:
            sel_day = st.selectbox(
                "상세 조회할 일자(Day) 선택:",
                options=active_day_list,
                index=len(active_day_list) - 1,
                format_func=lambda d: f"{year}년 {month:02d}월 {d:02d}일 ({len(df_month[df_month['day_num']==d])}건)",
                key="sel_cal_day_detail"
            )

        day_detail_df = df_month[df_month["day_num"] == sel_day].sort_values("start_time")
        st.markdown(f"**{year}년 {month:02d}월 {sel_day:02d}일** 작업 내역 (총 **{len(day_detail_df)}건** / **{round(day_detail_df['actual_hours'].sum(), 1)}시간**):")

        d_cols = st.columns(2)
        for idx, (_, r) in enumerate(day_detail_df.iterrows()):
            with d_cols[idx % 2]:
                w_name = r["worker_name"]
                w_team = r["worker_team"] or ""
                c_name = r["client_name"]
                t_desc = r["task_description"]
                st_t = r["start_time"].strftime("%H:%M") if pd.notna(r["start_time"]) else "?"
                ed_t = r["end_time"].strftime("%H:%M") if pd.notna(r["end_time"]) else "진행"
                act_h = r["actual_hours"]
                status_badge = "✅ 완료" if r["status"] == "COMPLETED" else "⏳ 진행중"

                st.markdown(f"""<div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;"><div style="display: flex; justify-content: space-between; margin-bottom: 4px;"><span style="font-weight: 700; color: #FFFFFF;">👤 {w_name} <span style="font-size: 11px; color: #38BDF8;">[{w_team}]</span></span><span style="font-size: 11px; color: #94A3B8;">{status_badge} ({st_t} ~ {ed_t} | {act_h}h)</span></div><div style="font-size: 13px; color: #38BDF8; font-weight: 600; margin-bottom: 2px;">🏢 {c_name}</div><div style="font-size: 12.5px; color: #CBD5E1;">{t_desc}</div></div>""", unsafe_allow_html=True)


def render_smart_search_tab(df_raw: pd.DataFrame, team_mappings: dict):
    """[🔍 전체 작업 스마트 검색] 다중 조건 실시간 통합 검색 탐색기"""
    st.markdown("### 🔍 전체 작업 통합 스마트 검색 & 다중 필터")
    st.caption("고객사명, 작업내용, 담당자, 소속팀, 야간/주말 여부 등 다중 조건을 조합하여 원하는 작업 이력을 0.1초 만에 실시간 검색합니다.")

    if df_raw.empty:
        st.info("검색할 작업 데이터가 존재하지 않습니다.")
        return

    search_df = df_raw.copy()
    if "worker_team" in search_df.columns:
        search_df["worker_team"] = search_df["worker_team"].fillna(search_df["worker_name"].map(team_mappings)).fillna(UNASSIGNED_TEAM)
    else:
        search_df["worker_team"] = search_df["worker_name"].map(team_mappings).fillna(UNASSIGNED_TEAM)

    # 1. 다중 스마트 필터 컨트롤 패널
    with st.expander("🛠️ 상세 검색 필터 설정 (여기를 클릭하여 조건 접기/펼치기)", expanded=True):
        f_col1, f_col2, f_col3 = st.columns([2, 1.5, 1.5])
        with f_col1:
            keyword = st.text_input("📝 통합 키워드 검색 (작업내용, 비고, 고객사)", placeholder="예: 정기점검, 장애처리, DR, 하나은행, BGF...", key="smart_kw")
        with f_col2:
            team_options = ["전체 팀"] + get_all_teams_safe() + [UNASSIGNED_TEAM]
            sel_team = st.selectbox("🏢 소속팀 필터:", options=team_options, index=0, key="smart_team")
        with f_col3:
            type_options = ["전체", "⏳ 실시간 진행중", "✅ 작업 완료", "🌙 야간 근무", "🏖️ 주말 근무", "🚨 예정시간 초과"]
            sel_type = st.selectbox("🏷️ 근무/상태 유형:", options=type_options, index=0, key="smart_type")

        f_col4, f_col5, f_col6 = st.columns([1.5, 1.5, 2])
        with f_col4:
            all_clients = sorted([c for c in search_df["client_name"].dropna().unique() if str(c).strip()])
            sel_clients = st.multiselect("🏢 고객사 다중 선택:", options=all_clients, placeholder="고객사 선택 (전체)", key="smart_clients")
        with f_col5:
            all_workers = sorted([w for w in search_df["worker_name"].dropna().unique() if str(w).strip()])
            sel_workers = st.multiselect("👤 작업자 다중 선택:", options=all_workers, placeholder="작업자 선택 (전체)", key="smart_workers")
        with f_col6:
            min_date = search_df["start_time"].dt.date.min() if pd.notna(search_df["start_time"].min()) else datetime.now().date()
            max_date = search_df["start_time"].dt.date.max() if pd.notna(search_df["start_time"].max()) else datetime.now().date()
            date_range = st.date_input("📅 작업 기간 범위:", value=(min_date, max_date), key="smart_date_range")

    # 2. 필터링 로직 적용
    filtered_df = search_df.copy()

    # 키워드 검색
    if keyword and keyword.strip():
        kw = keyword.strip().lower()
        filtered_df = filtered_df[
            filtered_df["task_description"].fillna("").str.lower().str.contains(kw, na=False) |
            filtered_df["client_name"].fillna("").str.lower().str.contains(kw, na=False) |
            filtered_df["worker_name"].fillna("").str.lower().str.contains(kw, na=False) |
            filtered_df["remarks"].fillna("").str.lower().str.contains(kw, na=False)
        ]

    # 팀 필터
    if sel_team != "전체 팀":
        filtered_df = filtered_df[filtered_df["worker_team"] == sel_team]

    # 근무/상태 유형 필터
    if sel_type == "⏳ 실시간 진행중":
        filtered_df = filtered_df[filtered_df["status"] == "PENDING"]
    elif sel_type == "✅ 작업 완료":
        filtered_df = filtered_df[filtered_df["status"] == "COMPLETED"]
    elif sel_type == "🌙 야간 근무":
        filtered_df = filtered_df[filtered_df["is_night_work"] == True]
    elif sel_type == "🏖️ 주말 근무":
        filtered_df = filtered_df[filtered_df["is_weekend_work"] == True]
    elif sel_type == "🚨 예정시간 초과":
        filtered_df = filtered_df[
            (filtered_df["estimated_hours"] > 0) & 
            (filtered_df["actual_hours"] > filtered_df["estimated_hours"])
        ]

    # 고객사 필터
    if sel_clients:
        filtered_df = filtered_df[filtered_df["client_name"].isin(sel_clients)]

    # 작업자 필터
    if sel_workers:
        filtered_df = filtered_df[filtered_df["worker_name"].isin(sel_workers)]

    # 날짜 범위 필터
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        st_d, ed_d = date_range
        filtered_df = filtered_df[
            (filtered_df["start_time"].dt.date >= st_d) & 
            (filtered_df["start_time"].dt.date <= ed_d)
        ]

    filtered_df = filtered_df.sort_values("start_time", ascending=False)

    # 3. 실시간 결과 핵심 요약 카드
    res_cnt = len(filtered_df)
    res_hours = round(filtered_df["actual_hours"].sum(), 1)
    res_workers = filtered_df["worker_name"].nunique()
    res_clients = filtered_df["client_name"].nunique()

    res_cards_html = f"""<div style="display: flex; gap: 12px; margin-top: 14px; margin-bottom: 18px; flex-wrap: wrap;"><div style="flex: 1; min-width: 140px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(0, 229, 255, 0.35); border-radius: 10px; padding: 12px 16px;"><div style="font-size: 12px; color: #94A3B8;">📋 검색된 작업</div><div style="font-size: 22px; font-weight: 800; color: #00E5FF;">{res_cnt:,}건</div></div><div style="flex: 1; min-width: 140px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(0, 230, 118, 0.35); border-radius: 10px; padding: 12px 16px;"><div style="font-size: 12px; color: #94A3B8;">⏱️ 총 투입 공수</div><div style="font-size: 22px; font-weight: 800; color: #00E676;">{res_hours:,}시간</div></div><div style="flex: 1; min-width: 140px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(179, 136, 255, 0.35); border-radius: 10px; padding: 12px 16px;"><div style="font-size: 12px; color: #94A3B8;">👥 투입 인원</div><div style="font-size: 22px; font-weight: 800; color: #B388FF;">{res_workers}명</div></div><div style="flex: 1; min-width: 140px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(251, 191, 36, 0.35); border-radius: 10px; padding: 12px 16px;"><div style="font-size: 12px; color: #94A3B8;">🏢 관련 고객사</div><div style="font-size: 22px; font-weight: 800; color: #FBBF24;">{res_clients}개사</div></div></div>"""
    st.markdown(res_cards_html, unsafe_allow_html=True)

    if filtered_df.empty:
        st.warning("🔍 설정하신 검색 조건에 부합하는 작업 내역이 없습니다. 다른 키워드나 조건으로 검색해 보세요.")
        return

    # 4. 결과 표출 뷰 (테이블 vs 카드 뷰)
    view_t1, view_t2 = st.tabs(["📋 인터랙티브 테이블 뷰", "📇 카드 상세 리스트 뷰"])

    with view_t1:
        # 다운로드 버튼
        export_df = filtered_df[[
            "id", "worker_name", "worker_team", "worker_title", "client_name", 
            "task_description", "start_time", "end_time", "actual_hours", 
            "estimated_hours", "status", "is_night_work", "is_weekend_work", "remarks"
        ]].copy()
        export_df["start_time"] = export_df["start_time"].dt.strftime("%Y-%m-%d %H:%M")
        export_df["end_time"] = export_df["end_time"].dt.strftime("%Y-%m-%d %H:%M")
        csv_data = export_df.to_csv(index=False, encoding="utf-8-sig")

        st.download_button(
            label="📥 검색 결과 엑셀(CSV) 다운로드",
            data=csv_data,
            file_name=f"작업검색결과_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key="dl_smart_search_csv"
        )

        display_df = export_df.rename(columns={
            "worker_name": "작업자",
            "worker_team": "소속팀",
            "worker_title": "직급",
            "client_name": "고객사",
            "task_description": "작업 내용",
            "start_time": "시작 시각",
            "end_time": "종료 시각",
            "actual_hours": "실제공수(h)",
            "estimated_hours": "예정공수(h)",
            "status": "상태",
            "is_night_work": "야간",
            "is_weekend_work": "주말",
            "remarks": "비고"
        })
        st.dataframe(display_df, use_container_width=True, height=450)

    with view_t2:
        st.caption(f"최신 작업 순으로 정렬된 상세 카드 목록입니다. (총 {res_cnt}건)")
        # 3열 그리드로 카드 표출 (최대 상위 60건)
        card_sub_df = filtered_df.head(60)
        c_cols = st.columns(3)
        for idx, (_, r) in enumerate(card_sub_df.iterrows()):
            with c_cols[idx % 3]:
                w_name = r["worker_name"]
                w_team = r["worker_team"] or ""
                w_title = r.get("worker_title") or ""
                c_name = r["client_name"]
                t_desc = r["task_description"]
                st_dt = r["start_time"]
                ed_dt = r["end_time"]
                act_h = r["actual_hours"]
                est_h = r["estimated_hours"]
                status = r["status"]

                st_str = st_dt.strftime("%m/%d %H:%M") if pd.notna(st_dt) else "?"
                ed_str = ed_dt.strftime("%H:%M") if pd.notna(ed_dt) else ("진행" if status == "PENDING" else "?")

                title_badge = f"<span style='background:rgba(255,255,255,0.08); padding:2px 5px; border-radius:4px; font-size:11px; margin-left:3px;'>{w_title}</span>" if w_title else ""
                team_badge = f"<span style='background:rgba(56,189,248,0.12); color:#38BDF8; padding:2px 5px; border-radius:4px; font-size:11px; margin-left:3px;'>{w_team}</span>"
                night_badge = "<span style='background:rgba(244,63,94,0.2); color:#F43F5E; padding:2px 5px; border-radius:4px; font-size:11px; margin-left:3px;'>🌙</span>" if r.get("is_night_work") else ""
                weekend_badge = "<span style='background:rgba(245,158,11,0.2); color:#F59E0B; padding:2px 5px; border-radius:4px; font-size:11px; margin-left:3px;'>🏖️</span>" if r.get("is_weekend_work") else ""

                status_badge = "<span style='background:rgba(0,230,118,0.15); color:#00E676; padding:2px 6px; border-radius:6px; font-size:10.5px; font-weight:700;'>⏳ 진행</span>" if status == "PENDING" else f"<span style='background:rgba(129,140,248,0.15); color:#818CF8; padding:2px 6px; border-radius:6px; font-size:10.5px; font-weight:700;'>✅ {act_h}h</span>"

                st.markdown(f"""<div style="background: linear-gradient(135deg, rgba(15,23,42,0.7) 0%, rgba(30,41,59,0.6) 100%); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 12px 14px; margin-bottom: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.25);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;"><div><span style="font-weight: 700; color: #FFFFFF; font-size: 14px;">👤 {w_name}</span>{title_badge}{team_badge}{night_badge}{weekend_badge}</div>{status_badge}</div><div style="font-size: 13.5px; color: #38BDF8; font-weight: 600; margin-bottom: 3px;">🏢 {c_name}</div><div style="font-size: 12.5px; color: #E2E8F0; line-height: 1.3; margin-bottom: 6px; min-height: 32px;">{t_desc}</div><div style="display: flex; justify-content: space-between; font-size: 11px; color: #94A3B8; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 4px;"><span>🕒 {st_str} ~ {ed_str}</span><span>예정: {est_h}h / 실: {act_h}h</span></div></div>""", unsafe_allow_html=True)

        if res_cnt > 60:
            st.info(f"💡 결과가 많아 상위 60건의 카드만 표시 중입니다. 전체 {res_cnt:,}건은 [📋 인터랙티브 테이블 뷰]에서 모두 확인 및 다운로드하실 수 있습니다.")





def render_team_management_page(all_workers_list, team_mappings):
    """[⚙️ 팀원 소속 및 직급 관리] 전용 관리 페이지 (신규 팀 생성 + 소속팀 + 직급 완벽 지원)"""
    st.header("⚙️ 팀원 소속 및 직급 관리 (팀 생성 & 배정)")
    st.markdown("부서/팀(`기술본부`, `기술 1팀`, `기술 2팀`, `기술 3팀`, `PI팀` 및 **직접 생성한 신규 팀**)별로 팀원의 **소속팀과 직급(`사원`, `대리`, `과장`, `수석`)**을 배정하고 자유롭게 생성/수정/해제할 수 있습니다.")
    st.divider()

    all_teams = get_all_teams_safe()
    COMPANY_TITLES = ["사원", "대리", "과장", "수석"]
    members_info = TeamService.get_team_members_info()

    # 0. 신규 팀 생성 및 팀 관리 섹션
    st.markdown("### 🏢 0. 신규 팀 생성 및 팀 목록 관리")
    st.caption("기본 팀(`기술본부`, `기술 1팀`, `기술 2팀`, `기술 3팀`, `PI팀`) 외에 필요한 **새로운 팀을 자유롭게 생성하거나 삭제**할 수 있습니다.")
    
    col_t_create, col_t_del = st.columns([1.2, 0.8])
    with col_t_create:
        c_in1, c_in2 = st.columns([2.5, 1.2])
        with c_in1:
            new_team_input = st.text_input("새 팀 이름 입력", placeholder="예: 인프라팀, 보안팀, 솔루션사업팀 등", label_visibility="collapsed", key="input_new_custom_team")
        with c_in2:
            if st.button("➕ 새 팀 생성", use_container_width=True, type="primary"):
                t_str = new_team_input.strip() if new_team_input else ""
                if t_str:
                    if t_str in all_teams:
                        st.warning(f"이미 존재하는 팀 이름입니다: {t_str}")
                    else:
                        TeamService.add_custom_team(t_str)
                        st.toast(f"🎉 [{t_str}] 팀이 성공적으로 생성되었습니다!", icon="✅")
                        st.rerun()
                else:
                    st.warning("생성할 팀 이름을 입력해주세요.")

    with col_t_del:
        custom_teams = [t for t in all_teams if t not in DEFAULT_TEAMS]
        if custom_teams:
            c_d1, c_d2 = st.columns([2.0, 1.2])
            with c_d1:
                del_pick = st.selectbox("삭제할 커스텀 팀", options=custom_teams, label_visibility="collapsed", key="del_team_pick_sb")
            with c_d2:
                if st.button("🗑️ 팀 삭제", use_container_width=True, help=f"[{del_pick}] 팀을 삭제하고 소속 인원을 '미지정'으로 전환합니다."):
                    TeamService.delete_custom_team(del_pick)
                    st.toast(f"🗑️ [{del_pick}] 팀이 삭제되었습니다.", icon="✅")
                    st.rerun()
        else:
            st.caption("💡 사용자가 직접 추가한 커스텀 팀이 있을 때 여기서 삭제할 수 있습니다.")

    st.divider()

    col_assign, col_status = st.columns([1.1, 0.9])

    # 1. 팀원별 소속팀 & 직급 개별 간편 설정
    with col_assign:
        st.markdown("### 📥 1. 팀원별 소속팀 & 직급 빠른 설정")
        st.caption("팀원을 선택하고 소속팀과 직급을 지정한 뒤 저장하시면 **DB와 작업 원장에 즉시 동기화**됩니다.")
        
        if all_workers_list:
            pick_worker = st.selectbox("1️⃣ 담당자 선택:", options=all_workers_list, key="pick_worker_manage")
            
            cur_worker_team = members_info.get(pick_worker, {}).get("team", "기술 1팀")
            cur_worker_title = members_info.get(pick_worker, {}).get("title", "")
            
            team_idx = all_teams.index(cur_worker_team) if cur_worker_team in all_teams else 0
            
            c_sel1, c_sel2 = st.columns(2)
            with c_sel1:
                sel_team = st.selectbox("2️⃣ 소속 팀 지정:", options=all_teams + [UNASSIGNED_TEAM], index=team_idx if team_idx < len(all_teams) else 0, key="sel_team_manage")
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
        
        # 전체 팀 현황 (동적 all_teams)
        for t_name in all_teams:
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
                st.success("모든 팀원이 소속 팀에 배정되어 있습니다.")

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
                options=all_teams + [UNASSIGNED_TEAM],
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
                "⚙️ 팀원 소속 및 직급 관리 (팀 생성/배정)",
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
    # 메뉴 분기 1: [⚙️ 팀원 소속 및 직급 관리] 메뉴 선택 시
    # ==========================================
    if "팀원 소속" in selected_menu:
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
                index=0,
                key="sb_filter_month_mode"
            )
            
            selected_months = []
            if month_mode == "전체 기간":
                selected_months = available_months
            elif month_mode == "특정 월 선택 (기본)":
                single_month = st.selectbox("조회할 월:", options=available_months, index=0, label_visibility="collapsed", key="sb_filter_single_month")
                selected_months = [single_month] if single_month else available_months
            else:
                selected_months = st.multiselect("조회할 월(다중):", options=available_months, default=available_months, label_visibility="collapsed", key="sb_filter_multi_months")

            # (2) 소속 팀 선택 (기본값: 기술 1팀)
            all_teams_filter = get_all_teams_safe()
            team_filter_options = ["전체 팀"] + all_teams_filter
            default_team_idx = team_filter_options.index("기술 1팀") if "기술 1팀" in team_filter_options else 0
            selected_team = st.selectbox("🏢 소속 팀:", options=team_filter_options, index=default_team_idx, key="sb_filter_team")

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
                index=0,
                key="sb_filter_worker_target_type"
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
                    label_visibility="collapsed",
                    key="sb_filter_workers"
                )

            # (4) 추가 상세 필터 (접이식 아코디언으로 정돈)
            with st.expander("🎯 추가 상세 필터 (고객사 / 작업구분 / 직급 / 야간·주말)", expanded=False):
                # 고객사 선택
                available_clients = sorted(df_raw["client_name"].dropna().unique())
                client_mode = st.radio("🏢 고객사 범위:", ["전체 고객사", "특정 고객사 선택"], horizontal=True, key="sb_filter_client_mode")
                selected_clients = available_clients if client_mode == "전체 고객사" else st.multiselect("고객사 선택:", options=available_clients, default=available_clients, label_visibility="collapsed", key="sb_filter_clients")

                # 작업구분 필터
                available_types = sorted(df_raw["log_type"].dropna().unique())
                type_mode = st.radio("🏷️ 작업 구분:", ["전체 구분", "특정 구분 선택"], horizontal=True, key="sb_filter_type_mode")
                selected_types = available_types if type_mode == "전체 구분" else st.multiselect("작업 구분 선택:", options=available_types, default=available_types, label_visibility="collapsed", key="sb_filter_types")

                # 👔 직급 필터 (사원 / 대리 / 과장 / 수석)
                title_mode = st.radio("👔 직급 범위:", ["전체 직급", "특정 직급 선택"], horizontal=True, key="sb_filter_title_mode")
                selected_titles = ["사원", "대리", "과장", "수석"] if title_mode == "전체 직급" else st.multiselect("직급 선택:", options=["사원", "대리", "과장", "수석"], default=["사원", "대리", "과장", "수석"], label_visibility="collapsed", key="sb_filter_titles")

                # 야간/주말 필터
                night_only = st.checkbox("🌙 야간 작업만 보기 (19시~08시)", key="sb_filter_night_only")
                weekend_only = st.checkbox("🏖️ 주말 작업만 보기", key="sb_filter_weekend_only")

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
                <div class="sb-sub">최근 수집: {countdown['last_run_str']} | {max(1, config.COLLECTOR_INTERVAL_SECONDS // 60)}분 주기 자동</div>
            </div>
            <script>
                let remaining = {countdown['remaining_seconds']};
                function updateSb() {{
                    let tEl = document.getElementById('sb-live-timer');
                    if (!tEl) return;
                    if (remaining <= 0) {{
                        tEl.innerText = "⚡ 지금 수집 중...";
                        tEl.style.color = "#00E676";
                    }} else {{
                        let m = Math.floor(remaining / 60);
                        let s = remaining % 60;
                        let sStr = s < 10 ? '0' + s : s;
                        tEl.innerText = (m > 0 ? m + "분 " : "") + sStr + "초 뒤";
                        tEl.style.color = "#FFFFFF";
                        remaining--;
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

        if st.button("🔄 실시간 Cloud DB 새로고침", key="btn_refresh_cloud_db", use_container_width=True, help="Supabase 클라우드 DB에서 최신 동기화 데이터를 즉시 다시 불러옵니다."):
            st.cache_data.clear()
            st.toast("☁️ 최신 클라우드 데이터를 불러왔습니다!", icon="✅")
            time.sleep(0.3)
            st.rerun()

        # ⏱️ 5분(300초) 무간섭 자동 실시간 화면 갱신 (Streamlit 공식 WebSocket 프로토콜 엔진)
        # iframe 보안 제약(cross-origin) 없이 어떤 PC/브라우저에서든 100% 확실하게 자동 갱신!
        # 사용자가 선택한 기간, 소속팀, 담당 팀원, 직급, 야간/주말 필터 설정 100% 완벽 보존!
        if st_autorefresh:
            refresh_count = st_autorefresh(interval=5 * 60 * 1000, key="auto_refresh_counter")
            st.markdown("""
            <div style="background: rgba(0, 230, 118, 0.08); border: 1px dashed rgba(0, 230, 118, 0.35); border-radius: 6px; padding: 5px 8px; text-align: center; margin-top: 4px;">
                <span style="font-size: 11px; color: #00E676; font-weight: 700;">🟢 5분 자동 실시간 동기화 가동 중 (필터 유지)</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            # Fallback
            st.markdown("""
            <meta http-equiv="refresh" content="300">
            """, unsafe_allow_html=True)

        # 3. 데이터 수동 동기화 (대화 파일 업로드)
        st.markdown('<div class="sidebar-section-header blue">📥 데이터 동기화 (파일 업로드)</div>', unsafe_allow_html=True)
        with st.expander("💬 카카오톡 대화 파일 업로드 (.txt)", expanded=False):
            uploaded_file = st.file_uploader("카카오톡 대화 텍스트 파일", type=["txt"], label_visibility="collapsed")
            if uploaded_file is not None:
                try:
                    file_content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
                    records = WorkLogMatcher.parse_and_match_text(file_content)
                    if records:
                        clear_all_web_caches()
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
            if st.button("🧹 캐시 초기화", use_container_width=True, help="DB 데이터는 안전하게 보존하고, 웹 대시보드 임시 캐시만 새로고침합니다."):
                clear_all_web_caches()
                st.toast("🧹 웹 캐시가 초기화되었습니다. 최신 DB 데이터를 다시 불러옵니다!", icon="✅")
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
    tab0, tab_cal, tab_search, tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🟢 오늘 실시간 라이브 현황 (Live)",
        "📅 작업 캘린더 & 밀도 히트맵",
        "🔍 전체 작업 스마트 검색",
        "👤 팀원별 업무량 분석",
        "🏢 팀별 업무량 비교",
        "📈 월별/일별 추이",
        "🏢 고객사별 공수 분포",
        "⏱️ 예정 vs 실제 소요시간"
    ])

    # ------------------------------------------
    # TAB 0: 오늘 실시간 작업 현황 라이브 보드
    # ------------------------------------------
    with tab0:
        render_today_live_board(df_raw, team_mappings, selected_team)

    # ------------------------------------------
    # TAB CAL: 작업 캘린더 & 밀도 히트맵
    # ------------------------------------------
    with tab_cal:
        render_calendar_and_heatmap_tab(df, df_raw, selected_team)

    # ------------------------------------------
    # TAB SEARCH: 전체 작업 스마트 검색
    # ------------------------------------------
    with tab_search:
        render_smart_search_tab(df_raw, team_mappings)

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
