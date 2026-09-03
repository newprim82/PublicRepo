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
import socket
import struct
from datetime import datetime, timedelta, timezone

from src.auth.auth_manager import AuthManager
from src.parser.reply_matcher import check_is_night_work, check_is_weekend_work

KST_TIMEZONE = timezone(timedelta(hours=9))

def get_current_kst_time() -> datetime:
    """한국 표준시(KST, UTC+9) 현재 시각 반환"""
    return datetime.now(KST_TIMEZONE)

def get_bora_ntp_timestamp() -> float:
    """time.bora.net (LGU+ 타임서버) NTP 기준 한국 표준시 타임스탬프(초) 반환 (네트워크 실패 시 시스템 KST fallback)"""
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(0.8)
        data = b'\x1b' + 47 * b'\0'
        client.sendto(data, ('time.bora.net', 123))
        resp, _ = client.recvfrom(1024)
        if resp:
            t = struct.unpack('!12I', resp)[10] - 2208988800
            return float(t)
    except Exception:
        pass
    return datetime.now(timezone.utc).timestamp()

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
    /* 🔤 토스(Toss) 표준 프리미엄 웹 폰트: Pretendard (프리텐다드) */
    @import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");

    /* 1. 사이트 전체 기본 본문 -> Pretendard (최고의 화면 가독성 & 선명도) */
    html, body, .stApp, .stApp *:not([data-testid*="Icon"]):not([data-testid*="icon"]):not(span[translate="no"]):not(svg) {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, "Segoe UI", sans-serif;
        letter-spacing: -0.2px;
    }

    /* 2. 모든 제목, 대형 KPI 수치 숫자, 타이틀 -> Pretendard 800 (ExtraBold) */
    h1, h2, h3, h4, h5, h6, 
    .kpi-value, 
    .kpi-value *,
    .kpi-title, 
    .main-title-text, 
    .main-title-text *,
    .sidebar-section-header,
    .filter-badge b,
    .alert-blink-badge,
    [data-testid="stMetricValue"],
    [data-testid="stMetricValue"] * {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, "Segoe UI", sans-serif !important;
        font-weight: 800 !important;
        letter-spacing: -0.4px;
    }

    /* 🚀 Streamlit 머티리얼 아이콘 폰트 (Material Symbols / Icons) 100% 온전하게 보존 */
    span[translate="no"],
    [data-testid*="Icon"],
    [data-testid*="icon"],
    [data-testid="stExpanderToggleIcon"],
    .material-symbols-rounded,
    .material-symbols-outlined,
    .material-icons {
        font-family: "Material Symbols Rounded", "Material Symbols Outlined", "Material Icons", sans-serif !important;
        font-weight: normal !important;
    }

    html {
        scroll-behavior: smooth;
    }
    /* 🏛️ Cisco ACI Enterprise 관제 포털 테마 (Light & Deep Cyan-Navy Hybrid) */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #f4f6f9 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Pretendard, sans-serif !important;
        color: #0f172a !important;
    }

    /* 🚀 타이틀 + 기준시각 & 우측 Deploy/점세개 최적화 */
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 0px !important;
        z-index: 100 !important;
    }

    /* 🚀 좌측 사이드바 열기 버튼 (stExpandSidebarButton: >>) */
    [data-testid="stExpandSidebarButton"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        pointer-events: auto !important;
        position: fixed !important;
        top: 1.15rem !important;
        left: 1.2rem !important;
        z-index: 999999 !important;
        background-color: #001e2d !important;
        color: #00b4d8 !important;
        border: 1.5px solid #00b4d8 !important;
        border-radius: 6px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2) !important;
    }
    [data-testid="stExpandSidebarButton"] svg {
        fill: #00b4d8 !important;
        color: #00b4d8 !important;
    }

    /* 🚀 좌측 사이드바 닫기 버튼 (stSidebarCollapseButton: <<) */
    [data-testid="stSidebarCollapseButton"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        pointer-events: auto !important;
    }
    [data-testid="stSidebarCollapseButton"] button {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        color: #00b4d8 !important;
        background: rgba(0, 180, 216, 0.12) !important;
        border: 1.5px solid #00b4d8 !important;
        border-radius: 6px !important;
    }
    [data-testid="stSidebarCollapseButton"] svg,
    [data-testid="stSidebarCollapseButton"] span {
        fill: #00b4d8 !important;
        color: #00b4d8 !important;
    }

    /* 🚀 우측 불필요한 Streamlit 툴바만 정밀 숨김 */
    [data-testid="stAppDeployButton"],
    [data-testid="stMainMenuButton"],
    [data-testid="stToolbarActions"],
    [data-testid="stToolbarActionButton"],
    .stDeployButton,
    #MainMenu {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        pointer-events: none !important;
    }
    .block-container {
        padding-top: 1.15rem !important;
        padding-bottom: 2rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }

    /* 🏛️ Cisco ACI 스타일 필터 배지 */
    .filter-badge {
        background-color: #e0f2fe !important;
        color: #0369a1 !important;
        padding: 9px 16px !important;
        border-radius: 8px !important;
        font-size: 13.5px !important;
        font-weight: 600 !important;
        display: inline-block !important;
        margin-bottom: 18px !important;
        border: 1px solid #bae6fd !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04) !important;
    }

    /* 🏛️ Cisco ACI 탭 바 완벽 카드형 배경 및 가독성 보장 */
    div[data-testid="stTabs"] [role="tablist"],
    div[data-testid="stTabs"] [data-baseweb="tab-list"],
    .stTabs [role="tablist"],
    .stTabs [data-baseweb="tab-list"] {
        display: flex !important;
        gap: 12px !important;
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        margin-bottom: 16px !important;
    }
    div[data-testid="stTabs"] [data-baseweb="tab-highlight"],
    div[data-testid="stTabs"] [data-baseweb="tab-border"],
    .stTabs [data-baseweb="tab-highlight"],
    .stTabs [data-baseweb="tab-border"] {
        display: none !important;
        height: 0px !important;
        background-color: transparent !important;
    }
    div[data-testid="stTabs"] button[role="tab"],
    div[data-testid="stTabs"] button[data-baseweb="tab"],
    .stTabs button[role="tab"],
    .stTabs button[data-baseweb="tab"] {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        height: 42px !important;
        min-height: 42px !important;
        white-space: nowrap !important;
        padding: 8px 20px !important;
        border-radius: 8px !important;
        font-size: 14px !important;
        font-weight: 800 !important;
        cursor: pointer !important;
        transition: all 0.2s ease !important;
    }
    /* 비선택 탭: 밝은 그레이 배경 + 선명한 다크네이비 글자 + 테두리 */
    div[data-testid="stTabs"] button[role="tab"]:not([aria-selected="true"]),
    div[data-testid="stTabs"] button[role="tab"][aria-selected="false"],
    div[data-testid="stTabs"] button[data-baseweb="tab"]:not([aria-selected="true"]),
    .stTabs button[role="tab"]:not([aria-selected="true"]) {
        background-color: #f1f5f9 !important;
        background: #f1f5f9 !important;
        border: 1.5px solid #cbd5e1 !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
    }
    div[data-testid="stTabs"] button[role="tab"]:not([aria-selected="true"]) *,
    div[data-testid="stTabs"] button[role="tab"][aria-selected="false"] *,
    div[data-testid="stTabs"] button[data-baseweb="tab"]:not([aria-selected="true"]) *,
    .stTabs button[role="tab"]:not([aria-selected="true"]) * {
        color: #002d42 !important;
        font-weight: 800 !important;
        font-size: 14px !important;
        opacity: 1 !important;
        visibility: visible !important;
    }
    div[data-testid="stTabs"] button[role="tab"]:not([aria-selected="true"]):hover,
    .stTabs button[role="tab"]:not([aria-selected="true"]):hover {
        background-color: #e2e8f0 !important;
        border-color: #94a3b8 !important;
    }
    /* 선택된 활성 탭: Cisco ACI 딥블루 배경 + 볼드 화이트 글자 */
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"],
    div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"],
    .stTabs button[role="tab"][aria-selected="true"] {
        background-color: #005073 !important;
        background: linear-gradient(135deg, #005073 0%, #003852 100%) !important;
        border: 1.5px solid #002233 !important;
        box-shadow: 0 3px 10px rgba(0, 80, 115, 0.35) !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] *,
    div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] *,
    .stTabs button[role="tab"][aria-selected="true"] * {
        color: #ffffff !important;
        font-weight: 900 !important;
        font-size: 14px !important;
        opacity: 1 !important;
        visibility: visible !important;
    }

    /* 🏛️ 전역 다운로드 버튼 스타일링 (선명한 화이트 볼드 텍스트) */
    div[data-testid="stDownloadButton"] button,
    [data-testid="stDownloadButton"] button,
    .stDownloadButton button {
        background: linear-gradient(135deg, #005073 0%, #003852 100%) !important;
        background-color: #005073 !important;
        color: #ffffff !important;
        border: 1px solid #002233 !important;
        border-radius: 6px !important;
        padding: 8px 18px !important;
        box-shadow: 0 2px 5px rgba(0, 80, 115, 0.3) !important;
    }
    div[data-testid="stDownloadButton"] button *,
    [data-testid="stDownloadButton"] button *,
    .stDownloadButton button * {
        color: #ffffff !important;
        font-weight: 800 !important;
        font-size: 13.5px !important;
        opacity: 1 !important;
        visibility: visible !important;
    }
    div[data-testid="stDownloadButton"] button:hover,
    [data-testid="stDownloadButton"] button:hover {
        background-color: #003852 !important;
    }
    div[data-testid="stDownloadButton"] button:hover * {
        color: #38bdf8 !important;
    }

    /* 🏛️ Cisco ACI 엔터프라이즈 화이트 KPI 카드 스타일 (완벽 중앙 정렬 & 입체감) */
    .kpi-card {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 10px !important;
        padding: 16px 14px !important;
        margin-bottom: 0px !important;
        box-shadow: 0 4px 16px rgba(0, 45, 66, 0.08), 0 1px 3px rgba(0, 0, 0, 0.05) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
        cursor: pointer !important;
        user-select: none;
        text-align: center !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
    }
    .kpi-card:hover {
        transform: translateY(-4px) !important;
        box-shadow: 0 10px 25px rgba(0, 45, 66, 0.15), 0 2px 6px rgba(0, 0, 0, 0.08) !important;
    }
    /* 🎨 5대 KPI 카드별 소프트 파스텔 그라데이션 및 상단 5px 컬러 바 */
    .kpi-card-hours {
        background: linear-gradient(180deg, #f0f9ff 0%, #ffffff 85%) !important;
        border: 1px solid #bae6fd !important;
        border-top: 5px solid #005073 !important;
    }
    .kpi-card-tasks {
        background: linear-gradient(180deg, #eff6ff 0%, #ffffff 85%) !important;
        border: 1px solid #bfdbfe !important;
        border-top: 5px solid #0284c7 !important;
    }
    .kpi-card-workers {
        background: linear-gradient(180deg, #f5f3ff 0%, #ffffff 85%) !important;
        border: 1px solid #ddd6fe !important;
        border-top: 5px solid #4f46e5 !important;
    }
    .kpi-card-urgent {
        background: linear-gradient(180deg, #fffbeb 0%, #ffffff 85%) !important;
        border: 1px solid #fde68a !important;
        border-top: 5px solid #ea580c !important;
    }
    .kpi-card-overdue-danger {
        background: linear-gradient(180deg, #fef2f2 0%, #ffffff 85%) !important;
        border: 1px solid #fca5a5 !important;
        border-top: 5px solid #dc2626 !important;
    }
    .kpi-card-overdue-safe {
        background: linear-gradient(180deg, #f0fdf4 0%, #ffffff 85%) !important;
        border: 1px solid #bbf7d0 !important;
        border-top: 5px solid #16a34a !important;
    }
    /* 🌟 5대 KPI 카드 투명 오버레이 버튼: 카드를 완벽하게 덮어서 원클릭 모달 오픈 유지 */
    div[data-testid="column"]:hover .kpi-card,
    div[data-testid="stColumn"]:hover .kpi-card {
        transform: translateY(-4px) !important;
        box-shadow: 0 10px 25px rgba(0, 45, 66, 0.15), 0 2px 6px rgba(0, 0, 0, 0.08) !important;
    }
    div.element-container:has(.kpi-card) + div.element-container {
        margin-top: -138px !important;
        height: 138px !important;
        position: relative !important;
        z-index: 20 !important;
    }
    div.element-container:has(.kpi-card) + div.element-container .stButton,
    div.element-container:has(.kpi-card) + div.element-container button,
    button[aria-label=" "] {
        height: 138px !important;
        min-height: 138px !important;
        width: 100% !important;
        background: transparent !important;
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: transparent !important;
        opacity: 0 !important;
        cursor: pointer !important;
        padding: 0 !important;
        margin: 0 !important;
    }

    .kpi-title {
        font-size: 16.5px !important;
        font-weight: 800 !important;
        color: #002d42 !important;
        text-transform: uppercase !important;
        padding-bottom: 8px !important;
        margin-bottom: 10px !important;
        border-bottom: 1.5px solid #e2e8f0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 100% !important;
        gap: 6px !important;
        letter-spacing: -0.3px !important;
        text-align: center !important;
    }
    .kpi-value {
        font-size: 35px !important;
        font-weight: 900 !important;
        line-height: 1.1 !important;
        margin-bottom: 10px !important;
        font-family: 'Segoe UI', Pretendard, sans-serif !important;
        color: #0f172a !important;
        display: flex !important;
        align-items: baseline !important;
        justify-content: center !important;
        width: 100% !important;
        text-align: center !important;
    }
    .kpi-unit {
        font-size: 15px !important;
        font-weight: 700 !important;
        color: #64748b !important;
        margin-left: 4px !important;
    }
    .kpi-badge {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 4px !important;
        padding: 4px 10px !important;
        border-radius: 6px !important;
        font-size: 12px !important;
        font-weight: 800 !important;
        letter-spacing: -0.2px !important;
        margin: 0 auto !important;
    }
    .badge-cyan { background-color: #e0f2fe !important; color: #0369a1 !important; border: 1px solid #bae6fd !important; }
    .badge-green { background-color: #d1e7dd !important; color: #0f5132 !important; border: 1px solid #a3cfbb !important; }
    .badge-purple { background-color: #ede9fe !important; color: #5b21b6 !important; border: 1px solid #c4b5fd !important; }
    .badge-amber { background-color: #fef3c7 !important; color: #d97706 !important; border: 1px solid #fde68a !important; }
    .badge-red { background-color: #fee2e2 !important; color: #dc2626 !important; border: 1px solid #fca5a5 !important; }
    /* 🏛️ Cisco APIC 트리 메뉴 사이드바 스타일링 */
    [data-testid="stSidebar"] {
        background-color: #002d42 !important;
        border-right: 1px solid #003852 !important;
    }
    [data-testid="stSidebar"] * {
        color: #bdcddc !important;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #00b4d8 !important;
    }
    [data-testid="stSidebar"] .block-container,
    [data-testid="stSidebarUserContent"] {
        padding-top: 0.4rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    [data-testid="stSidebarHeader"] {
        padding-top: 0.4rem !important;
        padding-bottom: 0.1rem !important;
    }
    /* 사이드바 내부 엘리먼트 초밀착 (APIC 트리 간격) */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"],
    [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] > div {
        gap: 1px !important;
    }
    [data-testid="stSidebar"] div.element-container {
        margin-top: 0px !important;
        margin-bottom: 0px !important;
        padding-top: 0px !important;
        padding-bottom: 0px !important;
    }
    /* 🌲 APIC 트리 노드 (Expander = 폴더/카테고리 헤더) */
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        margin-top: 0px !important;
        margin-bottom: 0px !important;
        border: none !important;
    }
    [data-testid="stSidebar"] details,
    [data-testid="stSidebar"] div[data-testid="stExpanderDetails"] {
        border: none !important;
        border-radius: 0px !important;
        background-color: transparent !important;
        background: transparent !important;
        padding-top: 0px !important;
        padding-bottom: 0px !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        font-weight: 800 !important;
        font-size: 13px !important;
        color: #ffffff !important;
        background-color: transparent !important;
        border-radius: 0px !important;
        border-bottom: 1px solid #1a5a73 !important;
        padding: 8px 8px 6px 8px !important;
        min-height: 28px !important;
        display: flex !important;
        align-items: center !important;
        letter-spacing: 0.3px !important;
        text-transform: uppercase !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary *,
    [data-testid="stSidebar"] [data-testid="stExpander"] summary p,
    [data-testid="stSidebar"] [data-testid="stExpander"] summary span {
        font-weight: 800 !important;
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover,
    [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover * {
        color: #00b4d8 !important;
        background-color: rgba(0, 180, 216, 0.06) !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary svg {
        fill: #4a7b94 !important;
        color: #4a7b94 !important;
        width: 14px !important;
        height: 14px !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover svg {
        fill: #00b4d8 !important;
        color: #00b4d8 !important;
    }
    /* 사이드바 내부 라벨 & 인풋 */
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown p {
        color: #e2e8f0 !important;
        font-weight: 600 !important;
    }
    /* 사이드바 셀렉트박스 완벽 복원 (글씨 선명한 흰색 & 배경 유지) */
    [data-testid="stSidebar"] [data-baseweb="select"] {
        background-color: #002d42 !important;
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] * {
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] > div {
        background-color: #002d42 !important;
        border: 1px solid #003852 !important;
        border-radius: 4px !important;
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] svg {
        fill: #00b4d8 !important;
        color: #00b4d8 !important;
    }
    /* 사이드바 라디오 & 체크박스 */
    [data-testid="stSidebar"] [data-baseweb="radio"] div {
        color: #bdcddc !important;
    }
    [data-testid="stSidebar"] [data-baseweb="checkbox"] span {
        color: #bdcddc !important;
    }
    /* 🌲 APIC 트리 아이템: 하위 메뉴 버튼에만 정밀하게 좌측 정렬 적용 (다른 위젯 간섭 0%) */
    [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button,
    [data-testid="stSidebar"] details .stButton > button {
        display: flex !important;
        justify-content: flex-start !important;
        align-items: center !important;
        text-align: left !important;
        border-radius: 0px !important;
        font-size: 12.5px !important;
        font-weight: 500 !important;
        background-color: transparent !important;
        border: none !important;
        border-left: 3px solid transparent !important;
        color: #bdcddc !important;
        transition: all 0.12s ease !important;
        padding: 6px 8px 6px 12px !important;
        min-height: 30px !important;
        width: 100% !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button div,
    [data-testid="stSidebar"] details .stButton > button div {
        justify-content: flex-start !important;
        text-align: left !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] details .stButton > button [data-testid="stMarkdownContainer"] {
        width: 100% !important;
        text-align: left !important;
        display: flex !important;
        justify-content: flex-start !important;
        align-items: center !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] details .stButton > button [data-testid="stMarkdownContainer"] p {
        text-align: left !important;
        width: 100% !important;
        margin: 0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button:hover,
    [data-testid="stSidebar"] details .stButton > button:hover {
        background-color: rgba(0, 180, 216, 0.10) !important;
        color: #ffffff !important;
        border-left: 3px solid #00b4d8 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button[kind="primary"],
    [data-testid="stSidebar"] details .stButton > button[kind="primary"] {
        background-color: rgba(0, 180, 216, 0.15) !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border-left: 3px solid #00b4d8 !important;
        border-radius: 0px !important;
        box-shadow: none !important;
    }
    /* 🏠 홈 버튼 빨간색 배경 & 중앙 정렬 (APIC 스타일 메인 네비게이션) */
    [data-testid="stSidebar"] .element-container:has(#home-nav-marker) + .element-container button {
        background-color: #b91c1c !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border-left: 3px solid #ef4444 !important;
        border-radius: 4px !important;
        padding: 7px 12px !important;
        justify-content: center !important;
        text-align: center !important;
    }
    [data-testid="stSidebar"] .element-container:has(#home-nav-marker) + .element-container button * {
        justify-content: center !important;
        text-align: center !important;
    }
    [data-testid="stSidebar"] .element-container:has(#home-nav-marker) + .element-container button:hover {
        background-color: #991b1b !important;
        border-left: 3px solid #f87171 !important;
    }

    /* 🏛️ Cisco ACI 표준 테이블 스타일링 */
    table {
        width: 100% !important;
        border-collapse: collapse !important;
        background: #ffffff !important;
        border-radius: 8px !important;
        overflow: hidden !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
        margin-bottom: 25px !important;
    }
    th {
        background-color: #005073 !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        padding: 12px 16px !important;
        text-align: left !important;
        font-size: 13.5px !important;
    }
    td {
        padding: 12px 16px !important;
        border-bottom: 1px solid #e1e4e8 !important;
        color: #334155 !important;
        font-size: 13.5px !important;
    }

    /* 🏛️ 과중 근무 알림 배너 */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) {
        background: #fff5f5 !important;
        border: 1.5px solid #fecaca !important;
        border-left: 8px solid #dc2626 !important;
        border-radius: 8px !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
        padding: 14px 20px !important;
        margin-top: 10px !important;
        margin-bottom: 6px !important;
    }
    /* 🚨 과중 근무 알림 배너 내부 버튼 및 사람 이름 칩 글자 선명한 흰색 볼드 표출 */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) .stButton > button,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) button {
        background-color: #1e293b !important;
        border: 1px solid #475569 !important;
        border-radius: 6px !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        font-size: 13px !important;
        padding: 4px 12px !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) .stButton > button *,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) button * {
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) .stButton > button:hover,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) button:hover {
        background-color: #334155 !important;
        border-color: #94a3b8 !important;
        color: #ffffff !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) .stButton > button:hover *,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.alert-blink-badge) button:hover * {
        color: #ffffff !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.normal-status-badge) {
        background: #f0fdf4 !important;
        border: 1.5px solid #bbf7d0 !important;
        border-left: 8px solid #16a34a !important;
        border-radius: 8px !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
        padding: 12px 20px !important;
        margin-top: 8px !important;
        margin-bottom: 6px !important;
        text-align: center !important;
    }
    .normal-status-badge {
        background: #d1e7dd !important;
        color: #0f5132 !important;
        border: 1px solid #a3cfbb !important;
        padding: 3px 12px !important;
        border-radius: 4px !important;
        font-weight: 700 !important;
        font-size: 13px !important;
        display: inline-flex !important;
        align-items: center !important;
    }
    .alert-blink-badge {
        background: #fee2e2 !important;
        color: #dc2626 !important;
        border: 1px solid #fca5a5 !important;
        padding: 3px 12px !important;
        border-radius: 4px !important;
        font-weight: 700 !important;
        font-size: 13px !important;
        display: inline-flex !important;
        align-items: center !important;
    }

    /* 🏛️ LIVE 관제 중 하위 통합 대형 네모 컨테이너 */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.live-board-main-container) {
        background: #ffffff !important;
        border: 1.5px solid #cbd5e1 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 18px rgba(0, 45, 66, 0.06), 0 1px 3px rgba(0, 0, 0, 0.04) !important;
        padding: 22px 24px 24px 24px !important;
        margin-top: 4px !important;
        margin-bottom: 24px !important;
    }

    /* 🚫 툴팁 오버레이 완전 차단 */
    div[data-baseweb="tooltip"],
    div[role="tooltip"],
    .stTooltipContent,
    [data-testid="stTooltipContent"],
    [data-testid="stTooltipHoverTarget"] div[data-baseweb="tooltip"] {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        pointer-events: none !important;
    }

    /* 🏛️ 팝업 모달 다이얼로그 (@st.dialog) 제목 및 닫기 버튼 흰색 스타일링 */
    div[data-testid="stDialog"] h1,
    div[data-testid="stDialog"] h2,
    div[data-testid="stDialog"] h3,
    div[data-testid="stDialog"] [data-testid="stHeadingWithActionElements"] h2,
    div[data-testid="stDialog"] [data-testid="stMarkdownContainer"] h2,
    div[data-testid="stDialog"] header,
    div[data-testid="stDialog"] header *,
    div[role="dialog"] h1,
    div[role="dialog"] h2,
    div[role="dialog"] h3,
    div[role="dialog"] [data-testid="stHeadingWithActionElements"] h2,
    div[role="dialog"] [data-testid="stMarkdownContainer"] h2,
    div[role="dialog"] header,
    div[role="dialog"] header *,
    div[data-baseweb="modal"] h1,
    div[data-baseweb="modal"] h2,
    div[data-baseweb="modal"] h3,
    div[data-baseweb="modal"] header,
    div[data-baseweb="modal"] header * {
        color: #ffffff !important;
        font-weight: 800 !important;
        fill: #ffffff !important;
    }
    div[data-testid="stDialog"] h1 *,
    div[data-testid="stDialog"] h2 *,
    div[data-testid="stDialog"] h3 *,
    div[role="dialog"] h1 *,
    div[role="dialog"] h2 *,
    div[role="dialog"] h3 * {
        color: #ffffff !important;
        fill: #ffffff !important;
    }
    div[data-testid="stDialog"] button[aria-label="Close"],
    div[data-testid="stDialog"] button[data-testid="stBaseButton-header"],
    div[role="dialog"] button[aria-label="Close"],
    div[role="dialog"] button[data-testid="stBaseButton-header"],
    div[data-baseweb="modal"] button[aria-label="Close"] {
        color: #ffffff !important;
    }
    div[data-testid="stDialog"] button[aria-label="Close"] svg,
    div[role="dialog"] button[aria-label="Close"] svg {
        fill: #ffffff !important;
        stroke: #ffffff !important;
    }

    /* 🏛️ 드롭다운 팝오버 및 셀렉트박스 옵션 가독성 */
    div[data-baseweb="popover"] {
        background-color: #ffffff !important;
        border: 1px solid #e1e4e8 !important;
        border-radius: 6px !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1) !important;
    }
    div[data-baseweb="popover"] *,
    ul[role="listbox"] * {
        color: #0f172a !important;
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
            
        title_mappings = TeamService.get_title_mappings()
        if title_mappings:
            df["worker_title"] = df["worker_name"].map(title_mappings).fillna(df.get("worker_title", ""))
            
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

        # 🌙 야간 작업(18시~06시 시작 & 1시간 이상) 및 🏖️ 주말 작업(1시간 이상 포함) 실시간 일관성 보장
        def _eval_night(row):
            try:
                st_val = row.get("start_time")
                if pd.isna(st_val) or not st_val:
                    return False
                if isinstance(st_val, str):
                    st_val = pd.to_datetime(st_val)
                if hasattr(st_val, "to_pydatetime"):
                    st_val = st_val.to_pydatetime()
                if getattr(st_val, "tzinfo", None) is not None:
                    st_val = st_val.replace(tzinfo=None)
                
                # 🌟 [절대 규칙] 시작 시각이 06:00~17:59인 주간 작업은 야간 판정 무조건 제외(False)
                if not (st_val.hour >= 18 or st_val.hour < 6):
                    return False

                act_m = int(row.get("actual_minutes") or 0)
                est_m = int(row.get("estimated_minutes") or 0)
                raw_msg = str(row.get("raw_start_message") or "") + " " + str(row.get("task_description") or "")
                return check_is_night_work(st_val, None, raw_msg, est_m, act_m)
            except Exception:
                return False

        def _eval_weekend(row):
            try:
                st_val = row.get("start_time")
                if pd.isna(st_val) or not st_val:
                    return False
                if isinstance(st_val, str):
                    st_val = pd.to_datetime(st_val)
                if hasattr(st_val, "to_pydatetime"):
                    st_val = st_val.to_pydatetime()
                if getattr(st_val, "tzinfo", None) is not None:
                    st_val = st_val.replace(tzinfo=None)
                act_m = int(row.get("actual_minutes") or 0)
                est_m = int(row.get("estimated_minutes") or 0)
                raw_msg = str(row.get("raw_start_message") or "") + " " + str(row.get("task_description") or "")
                return check_is_weekend_work(st_val, None, raw_msg, est_m, act_m)
            except Exception:
                return bool(row.get("is_weekend_work", False))

        df["is_night_work"] = df.apply(_eval_night, axis=1)
        df["is_weekend_work"] = df.apply(_eval_weekend, axis=1)

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


def strip_tz(df):
    """DataFrame 내 timezone-aware datetime 컬럼에서 +00:00 등 timezone 표시 제거"""
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]) and hasattr(df[col].dt, 'tz') and df[col].dt.tz is not None:
            df[col] = df[col].dt.tz_convert(None)
    return df


def inject_dialog_title_style():
    """모달 팝업 내부에서 상단 제목을 선명한 흰색으로 강제 주입"""
    st.markdown("""
    <style>
    div[data-testid="stDialog"] h1,
    div[data-testid="stDialog"] h2,
    div[data-testid="stDialog"] h3,
    div[data-testid="stDialog"] [data-testid="stHeadingWithActionElements"] h2,
    div[data-testid="stDialog"] [data-testid="stMarkdownContainer"] h2,
    div[data-testid="stDialog"] header,
    div[data-testid="stDialog"] header *,
    div[role="dialog"] h1,
    div[role="dialog"] h2,
    div[role="dialog"] h3,
    div[role="dialog"] [data-testid="stHeadingWithActionElements"] h2,
    div[role="dialog"] [data-testid="stMarkdownContainer"] h2,
    div[role="dialog"] header,
    div[role="dialog"] header *,
    div[data-baseweb="modal"] h1,
    div[data-baseweb="modal"] h2,
    div[data-baseweb="modal"] h3 {
        color: #ffffff !important;
        font-weight: 800 !important;
        fill: #ffffff !important;
    }
    div[data-testid="stDialog"] h1 *,
    div[data-testid="stDialog"] h2 *,
    div[data-testid="stDialog"] h3 *,
    div[role="dialog"] h1 *,
    div[role="dialog"] h2 *,
    div[role="dialog"] h3 * {
        color: #ffffff !important;
        fill: #ffffff !important;
    }
    div[data-testid="stDialog"] button[aria-label="Close"],
    div[role="dialog"] button[aria-label="Close"] {
        color: #ffffff !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ==========================================
# 팝업 대화상자 (모달 다이얼로그) - 최상단 전역 정의
# ==========================================
@st.dialog("🔍 세부 작업 내역 및 카카오톡 원본 분석", width="large")
def show_weekly_detail_dialog(target_worker: str, df_data: pd.DataFrame, default_week_name: str = None):
    inject_dialog_title_style()
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
                    input_leave_note = st.text_input("보상 내용 및 휴가 메모:", value="대체 휴무 1일 부여 완료" if default_leave_hrs >= 8.0 else "반차 부여 완료")
                
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
        disp_detail = strip_tz(detail.copy())
        if "end_time" not in disp_detail.columns:
            disp_detail["end_time"] = None
        if "status" in disp_detail.columns:
            disp_detail["status"] = disp_detail["status"].map({"PENDING": "진행 중", "COMPLETED": "완료"}).fillna(disp_detail["status"])
        st.dataframe(
            disp_detail[[
                "start_time", "end_time", "client_name", "task_description",
                "actual_hours", "status", "is_night_work"
            ]].rename(columns={
                "start_time": "시작 보고시각",
                "end_time": "완료 보고시각",
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
    inject_dialog_title_style()
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
    disp_sorted_df = strip_tz(sorted_df.copy())
    if "end_time" not in disp_sorted_df.columns:
        disp_sorted_df["end_time"] = None
    if "status" in disp_sorted_df.columns:
        disp_sorted_df["status"] = disp_sorted_df["status"].map({"PENDING": "진행 중", "COMPLETED": "완료"}).fillna(disp_sorted_df["status"])
    
    st.markdown("#### 📋 전체 지원 작업 상세 목록")
    st.caption("💡 표에서 특정 행을 클릭하시면, 해당 작업의 **카카오톡 시작/완료 원본 메시지**를 바로 아래에서 확인하실 수 있습니다.")
    sel_tbl = st.dataframe(
        disp_sorted_df[[
            "start_time", "end_time", "worker_name", "worker_team",
            "client_name", "task_description", "estimated_hours", "actual_hours", "status"
        ]].rename(columns={
            "start_time": "시작 보고시각",
            "end_time": "완료 보고시각",
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
    inject_dialog_title_style()
    if df_data.empty:
        st.info("데이터가 없습니다.")
        return
    comp_df = df_data[df_data["status"] == "COMPLETED"].sort_values(by="start_time", ascending=False).reset_index(drop=True)
    pend_df = df_data[df_data["status"] != "COMPLETED"].sort_values(by="start_time", ascending=False).reset_index(drop=True)
    
    st.markdown(f"### 📋 총 작업 건수: **{len(df_data):,}건** (🟢 완료 {len(comp_df)}건 | 🟡 진행 중 {len(pend_df)}건)")
    
    t_tab1, t_tab2 = st.tabs([f"🟢 완료된 작업 ({len(comp_df)}건)", f"🟡 진행 중인 작업 ({len(pend_df)}건)"])
    with t_tab1:
        st.caption("💡 표에서 행을 클릭하시면 해당 작업의 **카카오톡 시작/완료 원본 메시지**가 아래에 표시됩니다.")
        disp_comp = strip_tz(comp_df.copy())
        if "end_time" not in disp_comp.columns:
            disp_comp["end_time"] = None
        sel_t1 = st.dataframe(
            disp_comp[[
                "start_time", "end_time", "worker_name", "worker_team",
                "client_name", "task_description", "estimated_hours", "actual_hours"
            ]].rename(columns={
                "start_time": "시작 보고시각",
                "end_time": "완료 보고시각",
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
            disp_pend = strip_tz(pend_df.copy())
            if "end_time" not in disp_pend.columns:
                disp_pend["end_time"] = None
            sel_t2 = st.dataframe(
                disp_pend[[
                    "start_time", "end_time", "worker_name", "worker_team",
                    "client_name", "task_description", "estimated_hours"
                ]].rename(columns={
                    "start_time": "시작 보고시각",
                    "end_time": "완료 보고시각",
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
    inject_dialog_title_style()
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
    inject_dialog_title_style()
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
            disp_night = strip_tz(night_df.copy())
            if "end_time" not in disp_night.columns:
                disp_night["end_time"] = None
            sel_u1 = st.dataframe(
                disp_night[[
                    "start_time", "end_time", "worker_name", "worker_team",
                    "client_name", "task_description", "actual_hours"
                ]].rename(columns={
                    "start_time": "시작 보고시각",
                    "end_time": "완료 보고시각",
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
            disp_weekend = strip_tz(weekend_df.copy())
            if "end_time" not in disp_weekend.columns:
                disp_weekend["end_time"] = None
            sel_u2 = st.dataframe(
                disp_weekend[[
                    "start_time", "end_time", "worker_name", "worker_team",
                    "client_name", "task_description", "actual_hours"
                ]].rename(columns={
                    "start_time": "시작 보고시각",
                    "end_time": "완료 보고시각",
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
    inject_dialog_title_style()
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
        
        disp_overdue = strip_tz(overdue_df.copy())
        if "end_time" not in disp_overdue.columns:
            disp_overdue["end_time"] = None
        sel_overdue = st.dataframe(
            disp_overdue[[
                "start_time", "end_time", "worker_name", "worker_team",
                "client_name", "task_description", "estimated_hours",
                "actual_hours", "diff_hours"
            ]].rename(columns={
                "start_time": "시작 보고시각",
                "end_time": "완료 보고시각",
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
    inject_dialog_title_style()
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
    disp_w_df = strip_tz(w_df.copy())
    if "end_time" not in disp_w_df.columns:
        disp_w_df["end_time"] = None
    if "status" in disp_w_df.columns:
        disp_w_df["status"] = disp_w_df["status"].map({"PENDING": "진행 중", "COMPLETED": "완료"}).fillna(disp_w_df["status"])
    sel_tbl = st.dataframe(
        disp_w_df[[
            "start_time", "end_time", "client_name", "task_description",
            "estimated_hours", "actual_hours", "status", "is_night_work", "is_weekend_work"
        ]].rename(columns={
            "start_time": "시작 보고시각",
            "end_time": "완료 보고시각",
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
    inject_dialog_title_style()
    w_df = df_data[df_data["worker_name"] == worker_name].copy()
    
    if "주말" in category:
        cat_df = w_df[w_df["is_weekend_work"] == True].sort_values(by="start_time", ascending=False).reset_index(drop=True)
        cat_icon = "🏖️"
        cat_name = "주말 작업 (야간포함)"
    elif "야간" in category:
        cat_df = w_df[(w_df["is_weekend_work"] == False) & (w_df["is_night_work"] == True)].sort_values(by="start_time", ascending=False).reset_index(drop=True)
        cat_icon = "🌙"
        cat_name = "평일 야간 작업 (18시~06시, 1h 이상)"
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
    
    disp_cat_df = strip_tz(cat_df.copy())
    if "end_time" not in disp_cat_df.columns:
        disp_cat_df["end_time"] = None
    if "status" in disp_cat_df.columns:
        disp_cat_df["status"] = disp_cat_df["status"].map({"PENDING": "진행 중", "COMPLETED": "완료"}).fillna(disp_cat_df["status"])
    sel_tbl = st.dataframe(
        disp_cat_df[[
            "start_time", "end_time", "client_name", "task_description",
            "estimated_hours", "actual_hours", "status"
        ]].rename(columns={
            "start_time": "시작 보고시각",
            "end_time": "완료 보고시각",
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


def get_job_title_badge(title: str) -> str:
    """직급별 고유 색상(수석=보라, 과장=블루, 대리=그린, 사원=앰버) 뱃지 HTML 생성"""
    if not title:
        return ""
    t = str(title).strip()
    if not t or t == "None":
        return ""
    if "수석" in t:
        return f"<span style='background:#ede9fe; color:#5b21b6; border:1px solid #c4b5fd; padding:1px 6px; border-radius:4px; font-size:11px; font-weight:800; margin-left:4px;'>{t}</span>"
    elif "과장" in t:
        return f"<span style='background:#e0f2fe; color:#0369a1; border:1px solid #bae6fd; padding:1px 6px; border-radius:4px; font-size:11px; font-weight:800; margin-left:4px;'>{t}</span>"
    elif "대리" in t:
        return f"<span style='background:#d1e7dd; color:#0f5132; border:1px solid #a3cfbb; padding:1px 6px; border-radius:4px; font-size:11px; font-weight:800; margin-left:4px;'>{t}</span>"
    elif "사원" in t:
        return f"<span style='background:#fef3c7; color:#d97706; border:1px solid #fde68a; padding:1px 6px; border-radius:4px; font-size:11px; font-weight:800; margin-left:4px;'>{t}</span>"
    else:
        return f"<span style='background:#f1f5f9; color:#475569; border:1px solid #cbd5e1; padding:1px 6px; border-radius:4px; font-size:11px; font-weight:800; margin-left:4px;'>{t}</span>"


def get_job_title_color(title: str) -> str:
    """직급별 대표 테두리 색상 코드 반환 (수석=#5b21b6, 과장=#0369a1, 대리=#0f5132, 사원=#d97706)"""
    if not title:
        return "#00b4d8"
    t = str(title).strip()
    if "수석" in t:
        return "#5b21b6"
    elif "과장" in t:
        return "#0369a1"
    elif "대리" in t:
        return "#0f5132"
    elif "사원" in t:
        return "#d97706"
    else:
        return "#00b4d8"


def get_job_title_bar_style(title: str):
    """직급별 프로그래스 바 그라데이션 및 보더 스타일 반환"""
    if not title:
        return "linear-gradient(90deg, #0284c7, #0369a1)", "1px solid #bae6fd"
    t = str(title).strip()
    if "수석" in t:
        return "linear-gradient(90deg, #8b5cf6, #5b21b6)", "1px solid #c4b5fd"
    elif "과장" in t:
        return "linear-gradient(90deg, #0284c7, #0369a1)", "1px solid #bae6fd"
    elif "대리" in t:
        return "linear-gradient(90deg, #10b981, #0f5132)", "1px solid #a3cfbb"
    elif "사원" in t:
        return "linear-gradient(90deg, #f59e0b, #d97706)", "1px solid #fde68a"
    else:
        return "linear-gradient(90deg, #0284c7, #0369a1)", "1px solid #bae6fd"


def get_job_title_rank(title: str) -> int:
    """직급 정렬 우선순위 점수 반환 (수석=1, 과장=2, 대리=3, 사원=4, 기타=99)"""
    if not title:
        return 99
    t = str(title).strip()
    if "수석" in t:
        return 1
    elif "과장" in t:
        return 2
    elif "대리" in t:
        return 3
    elif "사원" in t:
        return 4
    else:
        return 99


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

    # 3. 상단 실시간 요약 바 (Live Status Summary - 다크모드 NOC 커맨드 센터 스타일)
    summary_html = f"""<div style="background: linear-gradient(135deg, #002233 0%, #003a55 50%, #004d71 100%); border: 1px solid #005f8a; border-radius: 9px; padding: 13px 20px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px; box-shadow: 0 4px 14px rgba(0, 34, 51, 0.25);"><div style="display: flex; align-items: center; gap: 11px;"><span style="background-color: #dc2626; color: #ffffff; border: 1px solid #ef4444; border-radius: 12px; padding: 3px 10px; font-size: 11px; font-weight: 800; letter-spacing: 0.5px; box-shadow: 0 0 8px rgba(220, 38, 38, 0.4);">● LIVE 관제 중</span><span style="font-size: 16.5px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px; text-shadow: 0 1px 3px rgba(0,0,0,0.5);">오늘 ({today_date.strftime('%Y년 %m월 %d일')}) 실시간 현장 지원 현황</span><span style="font-size: 12px; color: #38bdf8; background-color: rgba(0, 180, 216, 0.22); border: 1px solid rgba(56, 189, 248, 0.5); padding: 3px 9px; border-radius: 6px; font-weight: 700;">선택: {selected_team}</span></div><div style="display: flex; align-items: center; gap: 20px; font-size: 13.5px; font-weight: 600;"><span style="color: #cbd5e1;">👥 오늘 투입: <b style="color: #38bdf8; font-size: 14.5px; font-weight: 800;">{tot_workers}명</b></span><span style="color: #cbd5e1;">⏳ 진행 중: <b style="color: #fbbf24; font-size: 14.5px; font-weight: 800;">{len(pend_df)}건</b></span><span style="color: #cbd5e1;">✅ 완료: <b style="color: #4ade80; font-size: 14.5px; font-weight: 800;">{len(comp_df)}건</b></span><span style="color: #cbd5e1;">⏱️ 총 지원 공수: <b style="color: #f472b6; font-size: 14.5px; font-weight: 800;">{tot_hours}시간</b></span></div></div>"""
    st.markdown(summary_html, unsafe_allow_html=True)

    if today_df.empty:
        st.info(f"☕ 오늘({today_date.strftime('%Y-%m-%d')}) [{selected_team}]에 등록된 실시간 작업 보고가 아직 없습니다. 카카오톡에 시작 보고가 올라오면 10분 내로 여기에 실시간으로 표시됩니다!")
        return

    # 4 & 5. 🏛️ LIVE 관제 중 하위 전체 내용을 하나로 묶는 대형 통합 네모 컨테이너
    with st.container(border=True):
        st.markdown('<span class="live-board-main-container" style="display:none;"></span>', unsafe_allow_html=True)

        # 4. 실시간 진행 중(PENDING) 작업 섹션 (팀 단위 그룹 렌더링)
        st.markdown(f"""<div style="font-size: 17px; font-weight: 800; color: #002d42; border-left: 4px solid #00b4d8; padding-left: 10px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">⏳ 실시간 진행 중인 작업 <span style="background: #e0f2fe; color: #0369a1; border-radius: 12px; padding: 2px 9px; font-size: 12px; font-weight: 800;">{len(pend_df)}건</span></div>""", unsafe_allow_html=True)
        if pend_df.empty:
            st.success("🎉 현재 진행 중인 미완료 작업이 없습니다. 오늘 모든 작업이 성공적으로 완료되었습니다!")
        else:
            all_teams_order = get_all_teams_safe() + [UNASSIGNED_TEAM]
            active_teams = [t for t in all_teams_order if t in pend_df["worker_team"].values]
            for extra_t in pend_df["worker_team"].unique():
                if extra_t not in active_teams:
                    active_teams.append(extra_t)

            title_mappings = TeamService.get_title_mappings()

            for t_name in active_teams:
                t_pend = pend_df[pend_df["worker_team"] == t_name]
                if t_pend.empty:
                    continue

                # 🏆 직급 순서(수석 -> 과장 -> 대리 -> 사원)로 항상 정렬
                t_pend = t_pend.copy()
                t_pend["_rank_score"] = t_pend.apply(lambda r: get_job_title_rank(title_mappings.get(r["worker_name"]) or r.get("worker_title") or ""), axis=1)
                t_pend = t_pend.sort_values(by=["_rank_score", "start_time"], ascending=[True, False])

                # 웅장하고 눈에 확 띄는 프리미엄 팀 섹션 헤더 배너 (팀명 바로 옆에 건수 배지 배치)
                st.markdown(f"""<div style="margin-top: 14px; margin-bottom: 12px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 6px solid #005073; border-radius: 8px; padding: 9px 16px; display: flex; align-items: center; gap: 14px; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);"><span style="font-size: 16.5px; font-weight: 800; color: #002d42; letter-spacing: -0.3px;">🏢 {t_name}</span><span style="background-color: #d1e7dd; color: #0f5132; border: 1px solid #a3cfbb; padding: 2px 10px; border-radius: 20px; font-size: 11.5px; font-weight: 800;">🟢 {len(t_pend)}건 진행 중</span></div>""", unsafe_allow_html=True)

                p_cols = st.columns(4)
                for idx, (_, r) in enumerate(t_pend.iterrows()):
                    with p_cols[idx % 4]:
                        w_name = r["worker_name"]
                        w_title = title_mappings.get(w_name) or r.get("worker_title") or ""
                        title_str = get_job_title_badge(w_title)
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

                        rank_bar_bg, rank_bar_border = get_job_title_bar_style(w_title)
                        bar_bg = rank_bar_bg
                        bar_border = rank_bar_border
                        pct_text_color = get_job_title_color(w_title)
                        pct_display = f"{raw_pct}%"

                        time_str = st_dt.strftime("%H:%M") if pd.notna(st_dt) else "시각 미상"
                        is_night_flag = bool(r.get("is_night_work"))
                        if pd.notna(st_dt) and (6 <= st_dt.hour < 18):
                            is_night_flag = False
                        night_badge = "<span style='background:#fee2e2; color:#dc2626; padding:1px 5px; border-radius:4px; font-size:10px; font-weight:700; margin-left:3px;'>🌙 야간</span>" if is_night_flag else ""
                        weekend_badge = "<span style='background:#fef3c7; color:#d97706; padding:1px 5px; border-radius:4px; font-size:10px; font-weight:700; margin-left:3px;'>🏖️ 주말</span>" if r.get("is_weekend_work") else ""

                        rank_color = get_job_title_color(w_title)
                        border_color = rank_color
                        card_html = f"""<div style="background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid {border_color}; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;"><div><span style="font-size: 14px; font-weight: 700; color: #0f172a;">👤 {w_name}{title_str}</span>{night_badge}{weekend_badge}</div><span style="background-color: #d1e7dd; color: #0f5132; border: 1px solid #a3cfbb; border-radius: 6px; padding: 2px 8px; font-size: 11px; font-weight: 700;">시작 보고 시간 : {time_str}</span></div><div style="font-size: 13px; color: #005073; font-weight: 700; margin-bottom: 4px;">🏢 {c_name}</div><div style="position: relative; overflow: hidden; background: #e9ecef; border-radius: 6px; border: {bar_border}; margin-bottom: 5px; min-height: 28px; display: flex; align-items: center;"><div style="position: absolute; left: 0; top: 0; bottom: 0; width: {bar_width_pct}%; background: {bar_bg}; border-radius: 5px; transition: width 0.6s ease;\"\u003e</div><div style="position: relative; z-index: 2; width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 3px 8px; font-size: 11.5px; font-weight: 600; color: #ffffff; text-shadow: 0 1px 2px rgba(0,0,0,0.6); gap: 4px;"><span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 75%;">{t_desc}</span><span style="font-weight: 700; color: #ffffff; font-size: 10.5px; white-space: nowrap; background: rgba(0,0,0,0.4); padding: 1px 4px; border-radius: 4px;">{pct_display}</span></div></div><div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-top: 2px;"><span>⏱️ 예정: <b>{est_hours}h</b></span><span style="color: {'#dc2626; font-weight:700;' if is_overtime else '#0f5132;'}">⏱️ 경과: <b>{elapsed_hours}h</b> ({elapsed_mins}분) {'⚠️ 초과' if is_overtime else ''}</span></div></div>"""
                        st.markdown(card_html, unsafe_allow_html=True)

        st.markdown("<div style='margin-top: 22px; margin-bottom: 20px; border-top: 1.5px solid #e2e8f0;'></div>", unsafe_allow_html=True)

        # 5. 오늘 완료된 작업(COMPLETED) 섹션 (팀 단위 그룹 렌더링)
        st.markdown(f"""<div style="font-size: 17px; font-weight: 800; color: #002d42; border-left: 4px solid #10b981; padding-left: 10px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">✅ 오늘 완료된 작업 <span style="background: #ede9fe; color: #5b21b6; border-radius: 12px; padding: 2px 9px; font-size: 12px; font-weight: 800;">{len(comp_df)}건</span></div>""", unsafe_allow_html=True)
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

                # 🏆 직급 순서(수석 -> 과장 -> 대리 -> 사원)로 항상 정렬
                t_comp = t_comp.copy()
                t_comp["_rank_score"] = t_comp.apply(lambda r: get_job_title_rank(title_mappings.get(r["worker_name"]) or r.get("worker_title") or ""), axis=1)
                t_comp = t_comp.sort_values(by=["_rank_score", "start_time"], ascending=[True, False])

                # 웅장하고 눈에 확 띄는 프리미엄 완료 팀 섹션 헤더 배너 (팀명 바로 옆에 건수 배지 배치)
                st.markdown(f"""<div style="margin-top: 14px; margin-bottom: 10px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 6px solid #4f46e5; border-radius: 8px; padding: 9px 16px; display: flex; align-items: center; gap: 14px; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);"><span style="font-size: 16.5px; font-weight: 800; color: #002d42; letter-spacing: -0.3px;">🏢 {t_name}</span><span style="background-color: #ede9fe; color: #5b21b6; border: 1.5px solid #c4b5fd; padding: 2px 10px; border-radius: 20px; font-size: 11.5px; font-weight: 800;">✅ {len(t_comp)}건 완료</span></div>""", unsafe_allow_html=True)

                c_cols = st.columns(4)
                for idx, (_, r) in enumerate(t_comp.iterrows()):
                    with c_cols[idx % 4]:
                        w_name = r["worker_name"]
                        w_title = title_mappings.get(w_name) or r.get("worker_title") or ""
                        title_str = get_job_title_badge(w_title)
                        c_name = r["client_name"]
                        t_desc = r["task_description"]
                        st_dt = r["start_time"]
                        ed_dt = r["end_time"]
                        act_h = r["actual_hours"]

                        st_str = st_dt.strftime("%H:%M") if pd.notna(st_dt) else "?"
                        ed_str = ed_dt.strftime("%H:%M") if pd.notna(ed_dt) else "완료"

                        comp_border = get_job_title_color(w_title)
                        comp_html = f"""<div style="background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid {comp_border}; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;"><div><span style="font-size: 13.5px; font-weight: 700; color: #0f172a;">👤 {w_name}{title_str}</span></div><span style="background-color: #ede9fe; color: #5b21b6; border: 1px solid #c4b5fd; border-radius: 10px; padding: 1px 6px; font-size: 10px; font-weight: 700;">✅ {st_str}~{ed_str} ({act_h}h)</span></div><div style="font-size: 13px; color: #005073; font-weight: 700; margin-bottom: 3px;">🏢 {c_name}</div><div style="font-size: 12px; color: #475569; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{t_desc}</div></div>"""
                        st.markdown(comp_html, unsafe_allow_html=True)


@st.dialog("📅 일자별 세부 작업 내역", width="large")
def show_calendar_day_dialog(date_title: str, day_df: pd.DataFrame):
    """캘린더 날짜 클릭 시 열리는 상세 작업 내역 모달 팝업"""
    inject_dialog_title_style()
    st.subheader(f"📅 {date_title} 작업 상세 목록 (총 {len(day_df)}건)")

    if day_df.empty:
        st.info("해당 일자에 등록된 작업 내역이 없습니다.")
        return

    tot_h = round(day_df["actual_hours"].sum(), 1)
    tot_w = day_df["worker_name"].nunique()
    tot_c = day_df["client_name"].nunique()
    comp_cnt = int((day_df["status"] == "COMPLETED").sum())
    pend_cnt = int((day_df["status"] == "PENDING").sum())

    # 상단 요약 미니 배너
    st.markdown(f"""<div style="display: flex; gap: 10px; margin-bottom: 16px; background: #ffffff; border: 1px solid #e1e4e8; border-radius: 8px; padding: 10px 14px; flex-wrap: wrap; box-shadow: 0 1px 3px rgba(0,0,0,0.05);"><span style="color: #005073; font-weight: 700;">⏱️ 총 공수: <b>{tot_h}h</b></span><span style="color: #cbd5e1;">|</span><span style="color: #4f46e5; font-weight: 700;">👥 투입 인원: <b>{tot_w}명</b></span><span style="color: #cbd5e1;">|</span><span style="color: #d97706; font-weight: 700;">🏢 고객사: <b>{tot_c}개사</b></span><span style="color: #cbd5e1;">|</span><span style="color: #0f5132; font-weight: 700;">✅ 완료 {comp_cnt}건 / ⏳ 진행 {pend_cnt}건</span></div>""", unsafe_allow_html=True)

    # 2열 상세 카드 그리드
    day_df_sorted = day_df.sort_values("start_time")
    c_cols = st.columns(2)
    for idx, (_, r) in enumerate(day_df_sorted.iterrows()):
        with c_cols[idx % 2]:
            w_name = r["worker_name"]
            w_team = r.get("worker_team") or ""
            w_title = r.get("worker_title") or ""
            c_name = r["client_name"]
            t_desc = r["task_description"]
            st_dt = r["start_time"]
            ed_dt = r["end_time"]
            act_h = r["actual_hours"]
            est_h = r.get("estimated_hours") or 0
            status = r["status"]

            st_str = st_dt.strftime("%H:%M") if pd.notna(st_dt) else "?"
            ed_str = ed_dt.strftime("%H:%M") if pd.notna(ed_dt) else ("진행" if status == "PENDING" else "?")

            title_badge = get_job_title_badge(w_title)
            team_badge = f"<span style='background:#e0f2fe; color:#0369a1; padding:2px 6px; border-radius:4px; font-size:11px; margin-left:4px;'>{w_team}</span>" if w_team else ""
            is_comp_night = bool(r.get("is_night_work"))
            if pd.notna(st_dt) and (6 <= st_dt.hour < 18):
                is_comp_night = False
            night_badge = "<span style='background:#fee2e2; color:#dc2626; padding:2px 6px; border-radius:4px; font-size:11px; margin-left:4px;'>🌙 야간</span>" if is_comp_night else ""
            weekend_badge = "<span style='background:#fef3c7; color:#d97706; padding:2px 6px; border-radius:4px; font-size:11px; margin-left:4px;'>🏖️ 주말</span>" if r.get("is_weekend_work") else ""

            status_badge = "<span style='background:#d1e7dd; color:#0f5132; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:700;'>⏳ 진행 중</span>" if status == "PENDING" else f"<span style='background:#ede9fe; color:#5b21b6; border:1px solid #c4b5fd; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:700;'>✅ {act_h}h 완료</span>"

            st.markdown(f"""<div style="background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #005073; border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;"><div><span style="font-size: 14.5px; font-weight: 700; color: #0f172a;">👤 {w_name}</span>{title_badge}{team_badge}{night_badge}{weekend_badge}</div>{status_badge}</div><div style="font-size: 13.5px; color: #005073; font-weight: 700; margin-bottom: 3px;">🏢 {c_name}</div><div style="font-size: 12.5px; color: #334155; line-height: 1.4; margin-bottom: 6px;">{t_desc}</div><div style="display: flex; justify-content: space-between; font-size: 11.5px; color: #64748b; border-top: 1px solid #f1f5f9; padding-top: 5px;"><span>🕒 {st_str} ~ {ed_str}</span><span>예정: {est_h}h / 실: {act_h}h</span></div></div>""", unsafe_allow_html=True)


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
    if selected_team != "전체 팀" and "worker_team" in base_cal_df.columns:
        base_cal_df = base_cal_df[base_cal_df["worker_team"] == selected_team]

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

def render_smart_search_tab(df_raw: pd.DataFrame, team_mappings: dict):
    """[🔍 전체 작업 스마트 검색] 다중 조건 실시간 통합 검색 탐색기"""
    # 🎨 스마트 검색 탭 전용 선명한 UI 스타일링 주입 (모든 버전의 Streamlit expander 및 input 완벽 호환)
    st.markdown("""
    <style>
        /* 1. 상세 검색 필터 expander 헤더 (Cisco 딥 네이비 바 + 볼드 화이트 글자) */
        [data-testid="stExpander"] details summary,
        [data-testid="stExpander"] summary,
        [data-testid="stExpanderSummary"],
        .streamlit-expanderHeader,
        div.streamlit-expanderHeader,
        details[data-testid="stExpander"] summary {
            background: linear-gradient(135deg, #002233 0%, #004d71 100%) !important;
            background-color: #002d42 !important;
            border: 1px solid #005f8a !important;
            border-radius: 8px !important;
            color: #ffffff !important;
            font-weight: 800 !important;
            padding: 10px 16px !important;
            box-shadow: 0 2px 6px rgba(0, 34, 51, 0.15) !important;
        }
        [data-testid="stExpander"] details summary *,
        [data-testid="stExpander"] summary *,
        [data-testid="stExpanderSummary"] *,
        .streamlit-expanderHeader *,
        details[data-testid="stExpander"] summary * {
            color: #ffffff !important;
            font-weight: 800 !important;
            font-size: 13.5px !important;
        }

        /* 2. 검색 입력 폼 (화이트 배경, 짙은 텍스트, 선명한 테두리) */
        div[data-testid="stMain"] div[data-testid="stExpander"] input,
        div[data-testid="stMain"] div[data-testid="stExpander"] select,
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="input"],
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="select"] > div,
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="base-input"],
        div[data-testid="stMain"] div[data-testid="stExpander"] div[data-testid="stDateInput"] input {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
            font-size: 13px !important;
        }
        div[data-testid="stMain"] div[data-testid="stExpander"] input::placeholder {
            color: #94a3b8 !important;
            font-weight: 500 !important;
        }
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="select"] span,
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="select"] div {
            color: #0f172a !important;
            font-weight: 600 !important;
        }
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="tag"] {
            background-color: #e0f2fe !important;
            color: #0369a1 !important;
            border: 1px solid #bae6fd !important;
            border-radius: 4px !important;
            font-weight: 700 !important;
        }
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="tag"] * {
            color: #0369a1 !important;
        }

        /* 3. 다운로드 버튼 (Cisco ACI Deep Blue + 볼드 화이트 글자 상시 노출) */
        div[data-testid="stMain"] .stDownloadButton button,
        div[data-testid="stMain"] [data-testid="stDownloadButton"] button,
        div[data-testid="stMain"] button[kind="primary"],
        div[data-testid="stMain"] button[data-testid="baseButton-secondary"]:has(p:contains("다운로드")),
        div[data-testid="stMain"] div.stDownloadButton > button {
            background: linear-gradient(135deg, #005073 0%, #003852 100%) !important;
            background-color: #005073 !important;
            color: #ffffff !important;
            border: 1px solid #002233 !important;
            font-weight: 800 !important;
            border-radius: 6px !important;
            padding: 8px 18px !important;
            box-shadow: 0 2px 5px rgba(0, 80, 115, 0.25) !important;
        }
        div[data-testid="stMain"] .stDownloadButton button *,
        div[data-testid="stMain"] [data-testid="stDownloadButton"] button *,
        div[data-testid="stMain"] div.stDownloadButton > button * {
            color: #ffffff !important;
            font-weight: 800 !important;
            font-size: 13px !important;
        }
        div[data-testid="stMain"] .stDownloadButton button:hover,
        div[data-testid="stMain"] [data-testid="stDownloadButton"] button:hover {
            background-color: #003852 !important;
            border-color: #001824 !important;
        }
        div[data-testid="stMain"] .stDownloadButton button:hover *,
        div[data-testid="stMain"] [data-testid="stDownloadButton"] button:hover * {
            color: #38bdf8 !important;
        }

    </style>
    """, unsafe_allow_html=True)

    st.markdown("### 🔍 전체 작업 통합 스마트 검색 & 다중 필터")
    st.caption("고객사명, 작업내용, 담당자, 소속팀, 야간/주말 여부 등 다중 조건을 조합하여 원하는 작업 이력을 0.1초 만에 실시간 검색합니다.")

    if df_raw.empty:
        st.info("검색할 작업 데이터가 존재하지 않습니다.")
        return

    search_df = df_raw.copy()
    
    # 누락될 수 있는 필수 컬럼 안전 기본값 초기화
    default_columns = {
        "id": 0,
        "worker_name": "",
        "worker_team": UNASSIGNED_TEAM,
        "worker_title": "",
        "client_name": "미지정",
        "task_description": "",
        "start_time": pd.NaT,
        "end_time": pd.NaT,
        "actual_hours": 0.0,
        "estimated_hours": 0.0,
        "status": "COMPLETED",
        "is_night_work": False,
        "is_weekend_work": False,
        "remarks": ""
    }
    for col_key, def_val in default_columns.items():
        if col_key not in search_df.columns:
            search_df[col_key] = def_val

    # 팀명 매핑 보정
    search_df["worker_team"] = search_df["worker_team"].fillna(search_df["worker_name"].map(team_mappings)).fillna(UNASSIGNED_TEAM)

    # 1. 다중 스마트 필터 컨트롤 패널 (라벨을 선명한 딥 네이비로 표출)
    with st.expander("🛠️ 상세 검색 필터 설정 (여기를 클릭하여 조건 접기/펼치기)", expanded=True):
        f_col1, f_col2, f_col3 = st.columns([2, 1.5, 1.5])
        with f_col1:
            st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 4px;">📝 통합 키워드 검색:</div>', unsafe_allow_html=True)
            keyword = st.text_input("통합 키워드 검색", placeholder="예: 정기점검, 장애처리, DR, 하나은행, BGF...", key="smart_kw", label_visibility="collapsed")
        with f_col2:
            st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 4px;">🏢 소속팀 필터:</div>', unsafe_allow_html=True)
            team_options = ["전체 팀"] + get_all_teams_safe() + [UNASSIGNED_TEAM]
            sel_team = st.selectbox("소속팀 필터:", options=team_options, index=0, key="smart_team", label_visibility="collapsed")
        with f_col3:
            st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 4px;">🏷️ 근무/상태 유형:</div>', unsafe_allow_html=True)
            type_options = ["전체", "⏳ 실시간 진행중", "✅ 작업 완료", "🌙 야간 근무", "🏖️ 주말 근무", "🚨 예정시간 초과"]
            sel_type = st.selectbox("근무/상태 유형:", options=type_options, index=0, key="smart_type", label_visibility="collapsed")

        f_col4, f_col5, f_col6 = st.columns([1.5, 1.5, 2])
        with f_col4:
            st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 4px;">🏢 고객사 다중 선택:</div>', unsafe_allow_html=True)
            all_clients = sorted([c for c in search_df["client_name"].dropna().unique() if str(c).strip()])
            sel_clients = st.multiselect("고객사 다중 선택:", options=all_clients, placeholder="고객사 선택 (전체)", key="smart_clients", label_visibility="collapsed")
        with f_col5:
            st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 4px;">👤 작업자 다중 선택:</div>', unsafe_allow_html=True)
            all_workers = sorted([w for w in search_df["worker_name"].dropna().unique() if str(w).strip()])
            sel_workers = st.multiselect("작업자 다중 선택:", options=all_workers, placeholder="작업자 선택 (전체)", key="smart_workers", label_visibility="collapsed")
        with f_col6:
            st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 4px;">📅 작업 기간 범위:</div>', unsafe_allow_html=True)
            min_date = search_df["start_time"].dt.date.min() if pd.notna(search_df["start_time"].min()) else datetime.now().date()
            max_date = search_df["start_time"].dt.date.max() if pd.notna(search_df["start_time"].max()) else datetime.now().date()
            date_range = st.date_input("작업 기간 범위:", value=(min_date, max_date), key="smart_date_range", label_visibility="collapsed")

    # 2. 필터링 로직 적용
    filtered_df = search_df.copy()

    # 키워드 검색
    if keyword and keyword.strip():
        kw = keyword.strip().lower()
        filtered_df = filtered_df[
            filtered_df["task_description"].fillna("").astype(str).str.lower().str.contains(kw, na=False) |
            filtered_df["client_name"].fillna("").astype(str).str.lower().str.contains(kw, na=False) |
            filtered_df["worker_name"].fillna("").astype(str).str.lower().str.contains(kw, na=False) |
            filtered_df["remarks"].fillna("").astype(str).str.lower().str.contains(kw, na=False)
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

    # 3. 실시간 결과 핵심 요약 카드 (메인 대시보드와 통일된 세련된 화이트 카드)
    res_cnt = len(filtered_df)
    res_hours = round(filtered_df["actual_hours"].sum(), 1)
    res_workers = filtered_df["worker_name"].nunique()
    res_clients = filtered_df["client_name"].nunique()

    res_cards_html = f"""<div style="display: flex; gap: 14px; margin-top: 14px; margin-bottom: 20px; flex-wrap: wrap;"><div style="flex: 1; min-width: 140px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #005073; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"><div style="font-size: 12.5px; font-weight: 700; color: #64748b; margin-bottom: 4px;">📋 검색된 작업</div><div style="font-size: 24px; font-weight: 900; color: #005073; letter-spacing: -0.5px;">{res_cnt:,}건</div></div><div style="flex: 1; min-width: 140px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #0284c7; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"><div style="font-size: 12.5px; font-weight: 700; color: #64748b; margin-bottom: 4px;">⏱️ 총 투입 공수</div><div style="font-size: 24px; font-weight: 900; color: #0284c7; letter-spacing: -0.5px;">{res_hours:,}시간</div></div><div style="flex: 1; min-width: 140px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #10b981; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"><div style="font-size: 12.5px; font-weight: 700; color: #64748b; margin-bottom: 4px;">👥 투입 인원</div><div style="font-size: 24px; font-weight: 900; color: #10b981; letter-spacing: -0.5px;">{res_workers}명</div></div><div style="flex: 1; min-width: 140px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #f59e0b; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"><div style="font-size: 12.5px; font-weight: 700; color: #64748b; margin-bottom: 4px;">🏢 관련 고객사</div><div style="font-size: 24px; font-weight: 900; color: #f59e0b; letter-spacing: -0.5px;">{res_clients}개사</div></div></div>"""
    st.markdown(res_cards_html, unsafe_allow_html=True)

    if filtered_df.empty:
        st.warning("🔍 설정하신 검색 조건에 부합하는 작업 내역이 없습니다. 다른 키워드나 조건으로 검색해 보세요.")
        return

    # 4. 결과 표출: 인터랙티브 테이블 뷰 및 엑셀(XLSX) 다운로드 단독 노출
    target_cols = [
        "id", "worker_name", "worker_team", "worker_title", "client_name", 
        "task_description", "start_time", "end_time", "actual_hours", 
        "estimated_hours", "status", "is_night_work", "is_weekend_work", "remarks"
    ]
    available_cols = [c for c in target_cols if c in filtered_df.columns]
    export_df = filtered_df[available_cols].copy()
    if "start_time" in export_df.columns:
        export_df["start_time"] = export_df["start_time"].apply(lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else "")
    if "end_time" in export_df.columns:
        export_df["end_time"] = export_df["end_time"].apply(lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else "")
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
    if "상태" in display_df.columns:
        display_df["상태"] = display_df["상태"].map({"PENDING": "진행 중", "COMPLETED": "완료"}).fillna(display_df["상태"])
    if "야간" in display_df.columns:
        display_df["야간"] = display_df["야간"].apply(lambda x: "Y" if x else "")
    if "주말" in display_df.columns:
        display_df["주말"] = display_df["주말"].apply(lambda x: "Y" if x else "")

    # 📊 엑셀(.xlsx) 파일 생성 및 다운로드 버튼
    import io
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        display_df.to_excel(writer, index=False, sheet_name="작업검색결과")
    excel_data = excel_buffer.getvalue()

    st.download_button(
        label="📥 검색 결과 엑셀(XLSX) 다운로드",
        data=excel_data,
        file_name=f"기술본부_작업검색결과_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_smart_search_xlsx"
    )

    st.dataframe(display_df, use_container_width=True, height=520)


def render_executive_summary_tab(df: pd.DataFrame, df_raw: pd.DataFrame, selected_team: str, team_mappings: dict):
    """[📊 경영진 보고용 Executive Summary] 주간/월간 회의 및 임원 보고용 핵심 요약 & A4 인쇄 모드"""
    if df.empty:
        st.info("표시할 보고서 데이터가 없습니다.")
        return

    # 상단 헤더 & 원클릭 인쇄/다운로드 툴바 (아담한 콤팩트 버튼 배치)
    h_col1, h_col2 = st.columns([3.2, 1.8])
    with h_col1:
        st.markdown(f"### 📊 {selected_team} - Summary")
        st.caption("주간/월간 전체 작업 실적 핵심 요약 브리핑과 A4 출력 서식을 제공합니다.")
    with h_col2:
        btn_c1, btn_c2 = st.columns([1, 1])
        with btn_c1:
            # 브라우저 부모 윈도우 인쇄 대화상자 직접 호출 (window.parent.print())
            st.components.v1.html(
                """
                <style>body { margin: 0; padding: 0; background: transparent; }</style>
                <button onclick="window.parent.print()" style="
                    background: rgba(37, 99, 235, 0.9);
                    color: #FFFFFF;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-size: 11.5px;
                    font-weight: 700;
                    cursor: pointer;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    gap: 4px;
                    width: 100%;
                    height: 32px;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                " onmouseover="this.style.background='#1D4ED8'" onmouseout="this.style.background='rgba(37, 99, 235, 0.9)'">
                    🖨️ A4 인쇄
                </button>
                """,
                height=36
            )
        with btn_c2:
            # 요약 데이터 엑셀(.xlsx) 다운로드
            import io
            summary_df = StatsService.get_worker_summary(df)
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                summary_df.to_excel(writer, index=False, sheet_name="팀원별실적요약")
            excel_data = excel_buffer.getvalue()
            st.download_button(
                label="📥 엑셀(XLSX) 저장",
                data=excel_data,
                file_name=f"기술본부_작업실적_Summary_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_exec_summary_xlsx"
            )

    st.write("")

    # =========================================================================
    # 0. 📅 보고서 조회 주기 선택 (월간 전체 종합 vs 각 주차별 상세 드릴다운)
    # =========================================================================
    df_scope = df.copy()
    available_weeks = []
    if "week_label" in df_scope.columns:
        raw_weeks = [w for w in df_scope["week_label"].dropna().unique() if str(w).strip()]
        try:
            available_weeks = sorted(raw_weeks, key=lambda x: int(''.join(filter(str.isdigit, str(x)))) if any(c.isdigit() for c in str(x)) else str(x))
        except Exception:
            available_weeks = sorted(raw_weeks)

    period_options = ["📅 월간 전체 종합"] + [f"📌 {w}" for w in available_weeks] if len(available_weeks) > 1 else ["📅 월간 전체 종합"]
    
    st.markdown("""
    <style>
        div[data-testid="stRadio"] > label {
            color: #002d42 !important;
            font-size: 14px !important;
            font-weight: 800 !important;
            margin-bottom: 6px !important;
        }
        div[data-testid="stRadio"] > label p {
            color: #002d42 !important;
            font-size: 14px !important;
            font-weight: 800 !important;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] {
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
        div[data-testid="stRadio"] div[role="radiogroup"] label {
            background: #f1f5f9 !important;
            border: 1.2px solid #cbd5e1 !important;
            border-radius: 6px !important;
            padding: 5px 12px !important;
            margin: 0 !important;
            cursor: pointer !important;
            transition: all 0.15s ease-in-out !important;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] label:hover {
            background: #e2e8f0 !important;
            border-color: #0284c7 !important;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] label p,
        div[data-testid="stRadio"] div[role="radiogroup"] label span {
            color: #002d42 !important;
            font-size: 13px !important;
            font-weight: 800 !important;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] label[data-checked="true"],
        div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {
            background: #005073 !important;
            border-color: #002d42 !important;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] label[data-checked="true"] p,
        div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) p,
        div[data-testid="stRadio"] div[role="radiogroup"] label[data-checked="true"] span,
        div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) span {
            color: #ffffff !important;
            font-weight: 900 !important;
        }
    </style>
    """, unsafe_allow_html=True)

    if len(period_options) > 1:
        sel_period = st.radio(
            "📅 **보고서 조회 주기 선택 (월간 / 주간 드릴다운)**",
            options=period_options,
            horizontal=True,
            key="exec_summary_period_selector"
        )
    else:
        sel_period = "📅 월간 전체 종합"

    # 선택된 주기에 따른 활성 데이터셋(df_active) 및 전기 비교 데이터(prev_df) 분기
    if sel_period != "📅 월간 전체 종합":
        target_week = sel_period.replace("📌 ", "").strip()
        df_active = df_scope[df_scope["week_label"] == target_week].copy()
        current_period_label = f"{selected_team} - {target_week}"
        is_weekly_view = True

        # 직전 주차 찾기 (WoW 전주 대비 계산)
        cur_w_idx = available_weeks.index(target_week) if target_week in available_weeks else -1
        prev_df = pd.DataFrame()
        if cur_w_idx > 0:
            prev_week_label = available_weeks[cur_w_idx - 1]
            prev_df = df_scope[df_scope["week_label"] == prev_week_label].copy()
    else:
        df_active = df_scope.copy()
        current_period_label = f"{selected_team} - 월간 전체"
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
            if selected_team != "전체":
                prev_df["worker_team"] = prev_df["worker_team"].fillna(prev_df["worker_name"].map(team_mappings)).fillna(UNASSIGNED_TEAM)
                prev_df = prev_df[prev_df["worker_team"] == selected_team]

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
    # 1. 🏛️ 경영진 5초 펄스 카드 (4대 핵심 지표 with MoM/WoW Delta)
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
    if "week_label" in df_active.columns:
        wk_agg = df_active.groupby(["worker_name", "week_label"])["actual_hours"].sum().reset_index()
        danger_workers = wk_agg[wk_agg["actual_hours"] > 52]["worker_name"].unique()
        caution_workers = wk_agg[(wk_agg["actual_hours"] > 40) & (wk_agg["actual_hours"] <= 52)]["worker_name"].unique()
        danger_names = list(danger_workers)
        caution_names = [w for w in caution_workers if w not in danger_names]

    danger_cnt = len(danger_names)
    caution_cnt = len(caution_names)
    safe_cnt = max(0, tot_workers - danger_cnt - caution_cnt)

    top3_share = round((client_agg.head(3).sum() / tot_hours) * 100, 1) if tot_hours > 0 else 0.0

    risk_status_html = "<span style='color:#16a34a; font-weight:800;'>🟢 법정 근로시간 안정 (주 52시간 초과 인원 없음)</span>" if danger_cnt == 0 else f"<span style='color:#dc2626; font-weight:800;'>🚨 주 52시간 초과 주의 ({danger_cnt}명: {', '.join(danger_names)})</span>"

    briefing_html = f"""
    <div style="background: #ffffff; border: 1.5px solid #005f8a; border-left: 6px solid #005073; border-radius: 12px; padding: 20px 24px; margin-bottom: 24px; box-shadow: 0 4px 16px rgba(0, 45, 66, 0.06);">
        <div style="font-size: 16px; font-weight: 800; color: #002d42; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span>📑 [경영진 핵심 요약 브리핑 & 액션 아이템]</span>
                <span style="font-size: 12px; color: #0284c7; background: #e0f2fe; padding: 2px 8px; border-radius: 4px; font-weight: 700;">조회 기준: {current_period_label}</span>
            </div>
            <div style="font-size: 12px; color: #64748b; font-weight: 600;">실시간 자동 분석 브리핑</div>
        </div>
        <div style="font-size: 13.5px; color: #1e293b; line-height: 1.85;">
            <div style="margin-bottom: 8px; background: #f8fafc; padding: 10px 14px; border-radius: 8px; border-left: 3px solid #0284c7;">
                📌 <b>핵심 실적 총괄</b>: 총 <b>{tot_workers}명</b>의 인원이 <b>{tot_clients}개사</b>를 대상으로 <b>{tot_cnt:,}건</b>의 작업을 수행하여 <b>총 {tot_hours:,}시간</b>의 현장 지원 공수를 투입했습니다. 주요 집중 고객사 Top 3는 {top_clients_str} 순입니다.
            </div>
            <div style="margin-bottom: 8px; background: #f8fafc; padding: 10px 14px; border-radius: 8px; border-left: 3px solid #f59e0b;">
                ⚠️ <b>운영 건전성 진단</b>: {risk_status_html} | 비정규 근무 비중은 <b>야간 {night_pct}% ({tot_night_hours}h)</b>, <b>주말 {wknd_pct}% ({tot_wknd_hours}h)</b>로 집계되었습니다.
            </div>
            <div style="background: #f8fafc; padding: 10px 14px; border-radius: 8px; border-left: 3px solid #10b981;">
                💡 <b>전략적 리소스 제언</b>: 상위 3개 고객사 공수 점유율이 <b>{top3_share}%</b>로 집중되어 있으므로, 차기 계획 시 집중 고객사 전담 엔지니어 피로도 관리 및 인력 교차 지원(Cross-Support) 편성을 권장합니다.
            </div>
        </div>
    </div>
    """
    st.markdown(briefing_html, unsafe_allow_html=True)

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

    gov_c1, gov_c2, gov_c3 = st.columns(3)
    with gov_c1:
        st.markdown(f"""
        <div style="background: #ffffff; border: 1.5px solid {'#fca5a5' if danger_cnt > 0 else '#e2e8f0'}; border-left: 4px solid {'#dc2626' if danger_cnt > 0 else '#16a34a'}; border-radius: 8px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
            <div style="font-size: 12px; font-weight: 700; color: #64748b;">🚨 주 52시간 초과 위험군</div>
            <div style="font-size: 22px; font-weight: 900; color: {'#dc2626' if danger_cnt > 0 else '#16a34a'}; margin-top: 2px;">{danger_cnt}명</div>
            <div style="font-size: 11.5px; color: #64748b; margin-top: 4px;">{', '.join(danger_names) if danger_names else '초과 인원 없음 (안전)'}</div>
        </div>
        """, unsafe_allow_html=True)
    with gov_c2:
        st.markdown(f"""
        <div style="background: #ffffff; border: 1.5px solid {'#fde68a' if caution_cnt > 0 else '#e2e8f0'}; border-left: 4px solid {'#d97706' if caution_cnt > 0 else '#16a34a'}; border-radius: 8px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
            <div style="font-size: 12px; font-weight: 700; color: #64748b;">⚠️ 주 40~52시간 관리 주의군</div>
            <div style="font-size: 22px; font-weight: 900; color: {'#d97706' if caution_cnt > 0 else '#16a34a'}; margin-top: 2px;">{caution_cnt}명</div>
            <div style="font-size: 11.5px; color: #64748b; margin-top: 4px;">집중 모니터링 대상</div>
        </div>
        """, unsafe_allow_html=True)
    with gov_c3:
        st.markdown(f"""
        <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-left: 4px solid #16a34a; border-radius: 8px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
            <div style="font-size: 12px; font-weight: 700; color: #64748b;">🟢 안정적 근로시간 준수군</div>
            <div style="font-size: 22px; font-weight: 900; color: #16a34a; margin-top: 2px;">{safe_cnt}명</div>
            <div style="font-size: 11.5px; color: #64748b; margin-top: 4px;">정상 범위 (주 40h 이하)</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")
    st.divider()

    # =========================================================================
    # 5. 🏢 고객사 포트폴리오 파레토 분석 & 주요 집계표
    # =========================================================================
    st.markdown("#### 🏢 3. 주요 고객사별 공수 투입 Top 10 및 파레토 분석")
    
    # 상위 10개 고객사 파레토 차트 렌더링
    top10_clients = client_agg.head(10).reset_index()
    top10_clients.columns = ["client_name", "actual_hours"]
    top10_clients["cum_pct"] = (top10_clients["actual_hours"].cumsum() / tot_hours) * 100 if tot_hours > 0 else 0

    fig_pareto = go.Figure()
    fig_pareto.add_trace(go.Bar(
        x=top10_clients["client_name"],
        y=top10_clients["actual_hours"],
        name="투입 공수(h)",
        marker=dict(color="#005073", line=dict(color="#002d42", width=1)),
        text=[f"{h:.1f}h" for h in top10_clients["actual_hours"]],
        textposition="auto"
    ))
    fig_pareto.add_trace(go.Scatter(
        x=top10_clients["client_name"],
        y=top10_clients["cum_pct"],
        name="누적 점유율(%)",
        yaxis="y2",
        mode="lines+markers+text",
        line=dict(color="#ea580c", width=2.5),
        marker=dict(size=7, color="#ea580c"),
        text=[f"{p:.1f}%" for p in top10_clients["cum_pct"]],
        textposition="top center"
    ))
    fig_pareto.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family="Pretendard, -apple-system, sans-serif", color="#002d42", size=12),
        height=350,
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
    cum_80_idx = len(top10_clients)
    for idx, pct in enumerate(top10_clients["cum_pct"]):
        if pct >= 80.0:
            cum_80_idx = idx + 1
            break

    if cum_80_idx <= 3:
        top_pareto_names = ", ".join(top10_clients.iloc[:cum_80_idx]["client_name"].tolist())
    else:
        top_3_names = ", ".join(top10_clients.iloc[:3]["client_name"].tolist())
        top_pareto_names = f"{top_3_names} 외 {cum_80_idx - 3}개사"

    top_pareto_pct = top10_clients.iloc[cum_80_idx - 1]["cum_pct"] if not top10_clients.empty else 0.0

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

    client_top10_rows = []
    for c_rank, (c_name, c_h) in enumerate(client_agg.head(10).items(), 1):
        sub_c_df = df_active[df_active["client_name"] == c_name]
        c_w_cnt = sub_c_df["worker_name"].nunique()
        c_cnt = len(sub_c_df)
        c_share = round((c_h / tot_hours) * 100, 1) if tot_hours > 0 else 0
        main_tasks = ", ".join(sub_c_df["task_description"].dropna().unique()[:2])

        client_top10_rows.append({
            "순위": f"{c_rank}위",
            "고객사명": c_name,
            "투입 인원": f"{c_w_cnt}명",
            "작업 건수": f"{c_cnt}건",
            "총 투입공수": f"{round(c_h, 1)}h",
            "공수 비중": f"{c_share}%",
            "주요 지원 작업": main_tasks
        })

    if client_top10_rows:
        st.dataframe(pd.DataFrame(client_top10_rows), use_container_width=True, hide_index=True)

    st.write("")
    st.divider()

    # =========================================================================
    # 6. 📈 주차별 공수 변동 추이 & 부서별 종합 집계표
    # =========================================================================
    st.markdown("#### 📈 4. 주차별 공수 변동 추이 & 부서별 종합 집계표")

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

    st.write("")
    st.divider()

    # =========================================================================
    # 7. 👥 핵심 기여 팀원 Top 5
    # =========================================================================
    st.markdown("#### 👥 5. 최다 공수 투입 핵심 팀원 Top 5")
    worker_summary = StatsService.get_worker_summary(df_active)
    if not worker_summary.empty:
        top5_workers = worker_summary.head(5).copy()
        top5_display = top5_workers.rename(columns={
            "worker_name": "팀원명",
            "worker_team": "소속팀",
            "worker_title": "직급",
            "total_hours": "총 투입공수(h)",
            "work_days": "근무일수",
            "avg_hours_per_day": "일평균공수(h)",
            "most_frequent_client": "주요 고객사"
        })
        st.dataframe(top5_display, use_container_width=True, hide_index=True)



def render_login_page():
    """🔐 기술본부 관리자 로그인 전용 페이지"""
    st.markdown("""
    <style>
        .login-card {
            background: linear-gradient(135deg, #002233 0%, #003a55 50%, #004d71 100%);
            border: 1px solid #005f8a;
            border-radius: 12px;
            padding: 32px 36px 24px 36px;
            box-shadow: 0 8px 32px rgba(0, 34, 51, 0.35);
            text-align: center;
            margin-bottom: 20px;
        }
        .login-title {
            font-size: 22px;
            font-weight: 800;
            color: #ffffff;
            letter-spacing: -0.4px;
            margin-top: 8px;
            text-shadow: 0 1px 3px rgba(0,0,0,0.5);
        }
        .login-sub {
            font-size: 12.5px;
            color: #94a3b8;
            margin-top: 6px;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    col_l, col_center, col_r = st.columns([1, 1.4, 1])
    with col_center:
        st.markdown("""
        <div class="login-card">
            <div style="font-size: 36px;">🔐</div>
            <div class="login-title">기술본부 관리자 로그인</div>
            <div class="login-sub">시스템 설정 및 작업 원장 관리를 위한 관리자 인증 (24시간 세션 유지)</div>
        </div>
        """, unsafe_allow_html=True)

        if AuthManager.is_authenticated():
            current_admin = AuthManager.get_current_user() or "newprim"
            st.success(f"✅ 현재 **{current_admin}** 계정으로 로그인되어 있습니다.")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("🏠 대시보드로 이동", use_container_width=True, type="primary"):
                    st.session_state["current_page"] = "🏠 실시간 분석 대시보드"
                    st.rerun()
            with col_b2:
                if st.button("🚪 로그아웃", use_container_width=True):
                    AuthManager.logout()
                    st.toast("👋 로그아웃되었습니다.", icon="ℹ️")
                    st.rerun()
            return

        with st.form("admin_login_form", clear_on_submit=False):
            u_input = st.text_input("👤 관리자 아이디 (ID)", placeholder="아이디 입력 (newprim)", key="login_id_field")
            p_input = st.text_input("🔑 비밀번호 (Password)", type="password", placeholder="비밀번호 입력", key="login_pw_field")
            
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            submit = st.form_submit_button("🔓 로그인 (Login)", type="primary", use_container_width=True)
            
            if submit:
                if AuthManager.login(u_input, p_input):
                    st.toast("🎉 로그인 성공! 모든 관리자 권한이 활성화되었습니다.", icon="✅")
                    st.session_state["current_page"] = "🏠 실시간 분석 대시보드"
                    st.rerun()
                else:
                    st.error("⚠️ 아이디 또는 비밀번호가 올바르지 않습니다.")


def render_team_management_page(all_workers_list, team_mappings):
    """[⚙️ 팀원 소속 및 직급 관리] 전용 관리 페이지 (신규 팀 생성 + 소속팀 + 직급 완벽 지원)"""
    # 🎨 Cisco ACI Deep Cyan-Navy 전용 프리미엄 테마 주입
    st.markdown("""
    <style>
        /* 🏢 관리 페이지 전용 Cisco ACI 테마 스타일링 */

        /* 1. Primary 액션 버튼 (새 팀 생성, 소속팀 및 직급 즉시 저장, 표 수정 내용 전체 저장) -> Cisco ACI Deep Blue */
        [data-testid="stMain"] div.stButton > button[kind="primary"] {
            background-color: #005073 !important;
            border: 1px solid #003852 !important;
            border-radius: 6px !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            font-size: 13.5px !important;
            padding: 6px 14px !important;
            box-shadow: 0 2px 5px rgba(0, 80, 115, 0.25) !important;
            transition: all 0.2s ease !important;
        }
        [data-testid="stMain"] div.stButton > button[kind="primary"] * {
            color: #ffffff !important;
            font-weight: 700 !important;
        }
        [data-testid="stMain"] div.stButton > button[kind="primary"]:hover {
            background-color: #003852 !important;
            border-color: #002233 !important;
            box-shadow: 0 3px 8px rgba(0, 80, 115, 0.4) !important;
        }

        /* 2. Secondary 버튼 (팀 삭제, ❌ 해제, 전체 일괄 해제) -> 소프트 레드 경고 버튼 */
        [data-testid="stMain"] div.stButton > button[kind="secondary"],
        [data-testid="stMain"] div.stButton > button:not([kind="primary"]) {
            background-color: #fee2e2 !important;
            border: 1.5px solid #fca5a5 !important;
            border-radius: 6px !important;
            color: #dc2626 !important;
            font-weight: 700 !important;
            font-size: 13px !important;
            padding: 5px 12px !important;
            transition: all 0.2s ease !important;
        }
        [data-testid="stMain"] div.stButton > button[kind="secondary"] *,
        [data-testid="stMain"] div.stButton > button:not([kind="primary"]) * {
            color: #dc2626 !important;
            font-weight: 700 !important;
        }
        [data-testid="stMain"] div.stButton > button[kind="secondary"]:hover,
        [data-testid="stMain"] div.stButton > button:not([kind="primary"]):hover {
            background-color: #fecaca !important;
            border-color: #f87171 !important;
            color: #b91c1c !important;
        }
        [data-testid="stMain"] div.stButton > button[kind="secondary"]:hover *,
        [data-testid="stMain"] div.stButton > button:not([kind="primary"]):hover * {
            color: #b91c1c !important;
        }

        /* 3. 텍스트 입력창 (st.text_input) -> 화이트 필드 & 딥 시안 포커스 */
        [data-testid="stMain"] [data-testid="stTextInput"] input {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
            padding: 6px 12px !important;
        }
        [data-testid="stMain"] [data-testid="stTextInput"] input:focus {
            border-color: #00b4d8 !important;
            box-shadow: 0 0 0 2px rgba(0, 180, 216, 0.2) !important;
        }
        [data-testid="stMain"] [data-testid="stTextInput"] input::placeholder {
            color: #94a3b8 !important;
        }

        /* 4. 셀렉트박스 (st.selectbox) -> 화이트 필드 & 네이비 텍스트 */
        [data-testid="stMain"] [data-baseweb="select"] {
            background-color: #ffffff !important;
            border-radius: 6px !important;
        }
        [data-testid="stMain"] [data-baseweb="select"] > div {
            background-color: #ffffff !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 6px !important;
        }
        [data-testid="stMain"] [data-baseweb="select"] * {
            color: #0f172a !important;
            font-weight: 600 !important;
        }
        [data-testid="stMain"] [data-baseweb="select"] svg {
            fill: #005073 !important;
        }

        /* 5. 코드 태그 (`코드`) -> ACI 소프트 시안 뱃지 */
        [data-testid="stMain"] code {
            background-color: #e0f2fe !important;
            color: #0369a1 !important;
            font-weight: 700 !important;
            border: 1px solid #bae6fd !important;
            border-radius: 4px !important;
            padding: 2px 6px !important;
        }

        /* 6. 아코디언 (st.expander) -> ACI 화이트 카드 & 좌측 딥 시안 라인 */
        [data-testid="stMain"] [data-testid="stExpander"] {
            background-color: #ffffff !important;
            border: 1.5px solid #cbd5e1 !important;
            border-left: 5px solid #005073 !important;
            border-radius: 8px !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04) !important;
            margin-bottom: 12px !important;
        }
        [data-testid="stMain"] [data-testid="stExpander"] details {
            background-color: #ffffff !important;
            border-radius: 8px !important;
        }
        [data-testid="stMain"] [data-testid="stExpander"] summary {
            background-color: #f8fafc !important;
            border-bottom: 1px solid #e2e8f0 !important;
            padding: 10px 16px !important;
            border-radius: 6px 6px 0 0 !important;
        }
        [data-testid="stMain"] [data-testid="stExpander"] summary span,
        [data-testid="stMain"] [data-testid="stExpander"] summary p {
            color: #005073 !important;
            font-weight: 800 !important;
            font-size: 14px !important;
        }
        [data-testid="stMain"] [data-testid="stExpander"] summary:hover {
            background-color: #f1f5f9 !important;
        }
        [data-testid="stMain"] [data-testid="stExpander"] summary svg {
            fill: #005073 !important;
        }
    </style>
    """, unsafe_allow_html=True)
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
                if st.button("🗑️ 팀 삭제", use_container_width=True):
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
                                if st.button("❌ 해제", key=f"del_indiv_{t_name}_{name}"):
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
                required=True
            ),
            "직급": st.column_config.SelectboxColumn(
                "직급",
                options=["사원", "대리", "과장", "수석", ""],
                required=False
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
    # Cisco Catalyst Center 네비게이션 상태 초기화
    # ==========================================
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "🏠 실시간 분석 대시보드"

    # ==========================================
    # 사이드바: Cisco Catalyst Center 5대 네비게이션 드로어
    # ==========================================
    with st.sidebar:
        # 🏛️ APIC 스타일 사이드바 헤더
        st.markdown("""
        <div style="padding: 12px 10px 10px 10px; margin-bottom: 4px; ">
            <div style="font-size: 15px; font-weight: 800; color: #00b4d8; letter-spacing: -0.3px;">기술본부 관제센터</div>
            <div style="font-size: 10px; color: #5a8a9e; margin-top: 2px; letter-spacing: 0.5px;">FIELD SUPPORT PORTAL</div>
        </div>
        """, unsafe_allow_html=True)

        # 🏠 최상단 독립 메인 버튼: 실시간 분석 대시보드 (위아래 30px 간격)
        st.markdown('<div style="height: 30px;"></div><span id="home-nav-marker" style="display:none;"></span>', unsafe_allow_html=True)
        is_main_active = (st.session_state.get("current_page") == "🏠 실시간 분석 대시보드")
        if st.button("🏠 실시간 분석 대시보드", key="btn_top_home_dashboard", type="primary" if is_main_active else "secondary", use_container_width=True):
            st.session_state["current_page"] = "🏠 실시간 분석 대시보드"
            st.rerun()
        st.markdown('<div style="height: 30px;"></div>', unsafe_allow_html=True)

        is_auth = AuthManager.is_authenticated()

        # 1. 📂 메인 메뉴 (로그인 시에만 노출)
        if is_auth:
            with st.expander("⚙ 관리", expanded=False):
                main_menu_items = [
                    "⚙️ 팀원 소속 및 직급 관리 (팀 생성/배정)",
                    "📋 작업 기록 원장 & 엑셀"
                ]
                for m_item in main_menu_items:
                    is_active = (st.session_state["current_page"] == m_item)
                    btn_prefix = "▸ " if is_active else "  "
                    if st.button(f"{btn_prefix}{m_item}", key=f"nav_main_{m_item}", use_container_width=True, type="primary" if is_active else "secondary"):
                        st.session_state["current_page"] = m_item
                        st.rerun()

        # 2. 🔍 조회 기준
        with st.expander("🔍 조회 기준", expanded=True):
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
                night_only = st.checkbox("🌙 야간 작업만 보기 (18시~06시, 1h 이상)", key="sb_filter_night_only")
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


        # 3. 📊 작업 디테일 (7대 세부 분석 화면 전환)
        with st.expander("📊 분석", expanded=False):
            detail_menu_items = [
                "📅 작업 캘린더 & 밀도 히트맵",
                "🔍 전체 작업 스마트 검색",
                "📊 Summary",
                "👤 팀원별 업무량 분석",
                "🏢 팀별 업무량 비교",
                "📈 월별/일별 추이",
                "🏢 고객사별 공수 분포",
                "⏱️ 예정 vs 실제 소요시간"
            ]
            for d_item in detail_menu_items:
                is_active = (st.session_state["current_page"] == d_item)
                btn_prefix = "▸ " if is_active else "  "
                if st.button(f"{btn_prefix}{d_item}", key=f"nav_detail_{d_item}", use_container_width=True, type="primary" if is_active else "secondary"):
                    st.session_state["current_page"] = d_item
                    st.rerun()

        # 4. 🤖 카카오톡 실시간 연동 (로그인 시에만 노출)
        if is_auth:
            with st.expander("🔄 연동", expanded=False):
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

                if st.button("⚡ [기술본부] 방 지금 즉시 긁어오기", key="btn_manual_kakao_sidebar", type="primary", use_container_width=True):
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

                if st.button("🔄 실시간 Cloud DB 새로고침", key="btn_refresh_cloud_db", use_container_width=True):
                    st.cache_data.clear()
                    st.toast("☁️ 최신 클라우드 데이터를 불러왔습니다!", icon="✅")
                    time.sleep(0.3)
                    st.rerun()

                # 5분 자동 실시간 화면 갱신
                if st_autorefresh:
                    refresh_count = st_autorefresh(interval=5 * 60 * 1000, key="auto_refresh_counter")
                    st.markdown("""
                    <div style="background: rgba(0, 230, 118, 0.08); border: 1px dashed rgba(0, 230, 118, 0.35); border-radius: 6px; padding: 5px 8px; text-align: center; margin-top: 4px;">
                        <span style="font-size: 11px; color: #00E676; font-weight: 700;">🟢 5분 자동 실시간 동기화 가동 중</span>
                    </div>
                    """, unsafe_allow_html=True)

                # 카카오톡 대화 파일 업로드 (.txt)
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

        # 5. 🛠️ 시스템 관리 (로그인 시에만 노출)
        if is_auth:
            with st.expander("🛠️ 시스템 관리", expanded=False):
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("🔄 새로고침", use_container_width=True):
                        st.cache_data.clear()
                        st.rerun()
                with col_btn2:
                    if st.button("🧹 캐시 초기화", use_container_width=True):
                        clear_all_web_caches()
                        st.toast("🧹 웹 캐시가 초기화되었습니다. 최신 DB 데이터를 다시 불러옵니다!", icon="✅")
                        st.rerun()

        # 6. 🔑 사이드바 최하단 독립 로그인 / 로그아웃 버튼 (실시간 대시보드 스타일)
        st.markdown('<div style="height: 25px;"></div><div style="border-top: 1px solid rgba(255,255,255,0.08); margin-bottom: 12px;"></div>', unsafe_allow_html=True)
        if not is_auth:
            is_login_active = (st.session_state.get("current_page") == "🔐 시스템 로그인")
            if st.button("🔑 Login", key="btn_sidebar_standalone_login", type="primary" if is_login_active else "secondary", use_container_width=True):
                st.session_state["current_page"] = "🔐 시스템 로그인"
                st.rerun()
        else:
            current_admin = AuthManager.get_current_user() or "newprim"
            if st.button(f"🚪 Logout ({current_admin})", key="btn_sidebar_standalone_logout", use_container_width=True):
                AuthManager.logout()
                st.toast("👋 로그아웃되었습니다. 일반 조회 모드로 전환됩니다.", icon="ℹ️")
                st.rerun()

    # 데이터가 없을 때 안내 화면
    if df_raw.empty:
        st.warning("⚠️ 현재 등록된 작업 로그 데이터가 없습니다.")
        st.info("💡 사이드바의 **[카카오톡 대화 파일 업로드]**를 통해 대화 텍스트(.txt)를 업로드하거나, PC 카카오톡 자동 수집기를 실행해주세요.")
        return

    # ==========================================
    # 상단 Cisco Catalyst Center 글로벌 네이비 플랫폼 헤더
    # ==========================================
    curr_page = st.session_state.get("current_page", "🏠 실시간 분석 대시보드")
    page_tag = curr_page.split(" ")[1] if " " in curr_page else curr_page
    bora_ts = get_bora_ntp_timestamp()
    initial_ms = int(bora_ts * 1000)

    import streamlit.components.v1 as components
    components.html(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;
            }}
            body {{
                background: transparent;
                overflow: hidden;
            }}
            .header-bar {{
                background: linear-gradient(135deg, #002233 0%, #003a55 50%, #004d71 100%);
                color: #ffffff;
                padding: 11px 20px 11px 18px;
                border-radius: 9px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                box-shadow: 0 4px 14px rgba(0, 34, 51, 0.25);
                border: 1px solid #005f8a;
            }}
            .header-left {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            .header-title {{
                font-size: 18.5px;
                font-weight: 800;
                color: #ffffff;
                letter-spacing: -0.4px;
                text-shadow: 0 1px 3px rgba(0,0,0,0.5);
            }}
            .header-tag {{
                background: rgba(0, 180, 216, 0.22);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.5);
                padding: 2px 8px;
                border-radius: 6px;
                font-size: 11.5px;
                font-weight: 700;
                margin-left: 4px;
            }}
            .header-right {{
                font-size: 12.5px;
                color: #94a3b8;
                display: flex;
                align-items: center;
                gap: 14px;
            }}
            .clock-box {{
                display: inline-flex;
                align-items: center;
                gap: 6px;
                background-color: rgba(15, 23, 42, 0.55);
                color: #e2e8f0;
                padding: 4px 13px;
                border-radius: 20px;
                font-weight: bold;
                border: 1px solid rgba(255, 255, 255, 0.16);
            }}
            #live-bora-clock {{
                color: #ffffff;
                font-weight: 700;
                font-family: 'Segoe UI', Pretendard, sans-serif;
                letter-spacing: -0.2px;
            }}
            .badge-bora {{
                background: #0284c7;
                color: #ffffff;
                font-size: 10px;
                font-weight: 800;
                padding: 1px 6px;
                border-radius: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="header-bar">
            <div class="header-left">
                <span class="header-title">📊 기술본부 현장 업무 관제 센터</span>
                <span class="header-tag">{page_tag}</span>
            </div>
            <div class="header-right">
                <span style="font-weight: 700; color: #4ade80;"><span style="color: #22c55e; text-shadow: 0 0 8px #22c55e;">●</span> 관제 포털 정상 가동</span>
                <span style="color: rgba(255,255,255,0.25);">|</span>
                <div class="clock-box">
                    <span>🕒</span>
                    <span id="live-bora-clock">로딩 중...</span>
                    <span class="badge-bora" title="LGU+ time.bora.net NTP 타임서버 실시간 동기화">time.bora.net·KST</span>
                </div>
            </div>
        </div>
        <script>
            let serverTime = {initial_ms};
            let clientStart = performance.now();
            function tickBoraClock() {{
                let current = new Date(serverTime + (performance.now() - clientStart));
                let formatter = new Intl.DateTimeFormat('ko-KR', {{
                    timeZone: 'Asia/Seoul',
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false
                }});
                let parts = formatter.formatToParts(current);
                let p = {{}};
                parts.forEach(x => p[x.type] = x.value);
                let el = document.getElementById('live-bora-clock');
                if (el) {{
                    el.innerText = p.year + '-' + p.month + '-' + p.day + ' ' + p.hour + ':' + p.minute + ':' + p.second;
                }}
            }}
            setInterval(tickBoraClock, 1000);
            tickBoraClock();
        </script>
    </body>
    </html>
    """, height=56)

    # 0) 🔐 로그인 페이지
    if curr_page == "🔐 시스템 로그인":
        render_login_page()
        return

    # 🔒 관리자 전용 페이지 가드 (비인가 접근 시 로그인 화면으로 유도)
    admin_only_pages = [
        "⚙️ 팀원 소속 및 직급 관리 (팀 생성/배정)",
        "📋 작업 기록 원장 & 엑셀"
    ]
    if curr_page in admin_only_pages and not AuthManager.is_authenticated():
        st.warning("🔒 관리자 로그인이 필요한 메뉴입니다. 아래에서 먼저 로그인해주세요.")
        render_login_page()
        return

    # 1) 팀원 소속 및 직급 관리 페이지
    if curr_page == "⚙️ 팀원 소속 및 직급 관리 (팀 생성/배정)":
        render_team_management_page(all_workers_list, team_mappings)
        return

    # 2) 작업 기록 원장 & 엑셀
    if curr_page == "📋 작업 기록 원장 & 엑셀":
        st.subheader("📋 작업 지원 상세 기록 원장 & 엑셀 다운로드")
        
        # 🎨 Cisco ACI 다운로드 버튼 전용 스타일링 (글자 선명한 흰색 볼드 강제)
        st.markdown("""
        <style>
            div.stDownloadButton > button {
                background-color: #005073 !important;
                border: 1.5px solid #003852 !important;
                border-radius: 6px !important;
                color: #ffffff !important;
                font-weight: 700 !important;
                font-size: 13.5px !important;
                padding: 6px 14px !important;
                box-shadow: 0 2px 5px rgba(0, 80, 115, 0.25) !important;
                transition: all 0.2s ease !important;
            }
            div.stDownloadButton > button *,
            div.stDownloadButton > button p,
            div.stDownloadButton > button span {
                color: #ffffff !important;
                font-weight: 700 !important;
                font-size: 13.5px !important;
            }
            div.stDownloadButton > button:hover {
                background-color: #003852 !important;
                border-color: #002233 !important;
                box-shadow: 0 3px 8px rgba(0, 80, 115, 0.4) !important;
            }
            div.stDownloadButton > button:hover * {
                color: #ffffff !important;
            }
        </style>
        """, unsafe_allow_html=True)
        
        # openpyxl은 타임존(tz-aware) datetime을 지원하지 않으므로 strip_tz 적용
        clean_df = strip_tz(df)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            clean_df.to_excel(writer, index=False, sheet_name="지원시간통계")
        excel_data = output.getvalue()
        
        btn_col, _ = st.columns([2.0, 5.0])
        with btn_col:
            st.download_button(
                label="📥 엑셀(.xlsx) 원장 다운로드",
                data=excel_data,
                file_name=f"작업지원시간_통계_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        display_cols = [
            "start_time", "status", "log_type", "worker_name", "worker_company", "worker_team",
            "client_name", "task_description", "estimated_hours", "actual_hours", "is_night_work", "is_weekend_work"
        ]
        available_display_cols = [c for c in display_cols if c in df.columns]
        disp_df_out = strip_tz(df[available_display_cols].copy())
        if "status" in disp_df_out.columns:
            disp_df_out["status"] = disp_df_out["status"].map({"PENDING": "진행 중", "COMPLETED": "완료"}).fillna(disp_df_out["status"])
        
        st.dataframe(
            disp_df_out.rename(columns={
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

    # ==========================================
    # 메인 캔버스 뷰 전환 라우터 (Cisco Catalyst Center 방식)
    # ==========================================
    if curr_page == "🏠 실시간 분석 대시보드":
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
            <div class="kpi-card kpi-card-hours">
                <div class="kpi-title">⏱️ 총 지원 시간</div>
                <div class="kpi-value" style="color: #005073;">{kpi['total_hours']:,}<span class="kpi-unit">시간</span></div>
                <div class="kpi-badge badge-cyan">⚡ 실시간 합산 집계</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(" ", key="kpi_btn_hours", use_container_width=True, help="클릭하여 총 지원 시간 상세 내역 팝업 열기"):
                show_kpi_total_hours_dialog(df)
            
        with kpi_col2:
            st.markdown(f"""
            <div class="kpi-card kpi-card-tasks">
                <div class="kpi-title">📋 총 작업 건수</div>
                <div class="kpi-value" style="color: #0284c7;">{kpi['total_tasks']:,}<span class="kpi-unit">건</span></div>
                <div class="kpi-badge badge-cyan">🟢 완료 {kpi['completed_tasks']}건 <span style="color:#94a3b8;">|</span> 🟡 진행 {kpi['pending_tasks']}건</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(" ", key="kpi_btn_tasks", use_container_width=True, help="클릭하여 총 작업 건수 상세 팝업 열기"):
                show_kpi_total_tasks_dialog(df)
            
        with kpi_col3:
            st.markdown(f"""
            <div class="kpi-card kpi-card-workers">
                <div class="kpi-title">👥 투입 인원 & 평균 공수</div>
                <div class="kpi-value" style="color: #4f46e5;">{kpi['active_workers']}<span class="kpi-unit">명</span></div>
                <div class="kpi-badge badge-purple">👤 1인당 평균 {kpi['avg_hours_per_worker']}h</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(" ", key="kpi_btn_workers", use_container_width=True, help="클릭하여 팀원별 공수 팝업 열기"):
                show_kpi_workers_dialog(df)
            
        with kpi_col4:
            total_urg = kpi['night_tasks_count'] + kpi['weekend_tasks_count']
            st.markdown(f"""
            <div class="kpi-card kpi-card-urgent">
                <div class="kpi-title">🌙 야간 / 주말 긴급 작업</div>
                <div class="kpi-value" style="color: #ea580c;">{total_urg}<span class="kpi-unit">건</span></div>
                <div class="kpi-badge badge-amber">🌙 야간 {kpi['night_tasks_count']}건 <span style="color:#94a3b8;">|</span> 🏖️ 주말 {kpi['weekend_tasks_count']}건</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(" ", key="kpi_btn_urgent", use_container_width=True, help="클릭하여 야간/주말 긴급 작업 팝업 열기"):
                show_kpi_urgent_dialog(df)
            
        with kpi_col5:
            overdue_val = float(kpi.get('overdue_rate', 0))
            overdue_cnt = int(kpi.get('overdue_tasks_count', 0))
            is_danger = (overdue_val > 0) or (overdue_cnt > 0)
            overdue_color = "#dc2626" if is_danger else "#16a34a"
            overdue_cls = "kpi-card-overdue-danger" if is_danger else "kpi-card-overdue-safe"
            badge_cls = "badge-red" if is_danger else "badge-green"
            badge_text = f"🚨 초과 {overdue_cnt}건 발생" if is_danger else "✅ 초과 없음"
            st.markdown(f"""
            <div class="kpi-card {overdue_cls}">
                <div class="kpi-title">⚠️ 예정 시간 초과율</div>
                <div class="kpi-value" style="color: {overdue_color};">{kpi['overdue_rate']}<span class="kpi-unit">%</span></div>
                <div class="kpi-badge {badge_cls}">{badge_text}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(" ", key="kpi_btn_overdue", use_container_width=True, help="클릭하여 예정 시간 초과 내역 팝업 열기"):
                show_kpi_overdue_dialog(df)

        # ----------------------------------------------------
        # 🚨 상단 과중 근무 실시간 감지 & 원클릭 보상휴가 팝업 배너
        # ----------------------------------------------------
        if not df.empty and "week_label" in df.columns:
            all_rewards = RewardLeaveService.get_all_reward_leaves()
            danger_items = []
            caution_items = []
            rewarded_items = []
            
            # 주차별/팀원별 집계
            wk_user_agg = df.groupby(["worker_name", "week_label"])["actual_hours"].sum().reset_index()
            for _, r in wk_user_agg.iterrows():
                w_name = r["worker_name"]
                w_lbl = r["week_label"]
                val = round(r["actual_hours"], 1)
                short_w = w_lbl.split(" ")[-2] if " " in w_lbl else w_lbl
                if val >= 40.0:
                    item = {
                        "worker_name": w_name,
                        "week_label": w_lbl,
                        "short_w": short_w,
                        "val": val,
                        "is_52": (val >= 52.0)
                    }
                    if (w_name, w_lbl) in all_rewards:
                        rewarded_items.append(item)
                    elif val >= 52.0:
                        danger_items.append(item)
                    else:
                        caution_items.append(item)

            if danger_items or caution_items or rewarded_items:
                with st.container(border=True):
                    # 배너 내부 버튼/칩 글자 가독성 (52h: 빨간색, 40h: 주황색, 보상완료: 초록색 배경)
                    st.markdown("""
                    <style>
                        /* 🚨 주 52시간 초과 버튼 (빨간색 배경) */
                        div.stButton > button[kind="primary"] {
                            background-color: #dc2626 !important;
                            border: 1.5px solid #b91c1c !important;
                            border-radius: 6px !important;
                            color: #ffffff !important;
                            font-weight: 700 !important;
                            font-size: 12px !important;
                            padding: 4px 6px !important;
                            box-shadow: 0 2px 5px rgba(220, 38, 38, 0.3) !important;
                        }
                        div.stButton > button[kind="primary"] * {
                            color: #ffffff !important;
                            font-weight: 700 !important;
                        }
                        div.stButton > button[kind="primary"]:hover {
                            background-color: #b91c1c !important;
                            border-color: #991b1b !important;
                        }

                        /* ⚠️ 주 40시간 초과 버튼 (주황색 배경) */
                        div.stButton > button[kind="secondary"],
                        div.stButton > button {
                            background-color: #ea580c !important;
                            border: 1.5px solid #c2410c !important;
                            border-radius: 6px !important;
                            color: #ffffff !important;
                            font-weight: 700 !important;
                            font-size: 12px !important;
                            padding: 4px 6px !important;
                            box-shadow: 0 2px 5px rgba(234, 88, 12, 0.3) !important;
                        }
                        div.stButton > button[kind="secondary"] *,
                        div.stButton > button * {
                            color: #ffffff !important;
                            font-weight: 700 !important;
                        }
                        div.stButton > button[kind="secondary"]:hover,
                        div.stButton > button:hover {
                            background-color: #c2410c !important;
                            border-color: #9a3412 !important;
                        }

                        /* ✅ 과중근무 보상완료 버튼 (초록색 배경) */
                        div.element-container:has(.reward-chip-zone) {
                            display: none !important;
                            height: 0px !important;
                            margin: 0px !important;
                            padding: 0px !important;
                        }
                        div[data-testid="stColumn"]:has(.reward-chip-zone) button,
                        div[data-testid="column"]:has(.reward-chip-zone) button {
                            background-color: #16a34a !important;
                            border: 1.5px solid #15803d !important;
                            border-radius: 6px !important;
                            color: #ffffff !important;
                            font-weight: 700 !important;
                            font-size: 12px !important;
                            padding: 4px 6px !important;
                            box-shadow: 0 2px 5px rgba(22, 163, 74, 0.3) !important;
                        }
                        div[data-testid="stColumn"]:has(.reward-chip-zone) button *,
                        div[data-testid="column"]:has(.reward-chip-zone) button * {
                            color: #ffffff !important;
                            font-weight: 700 !important;
                        }
                        div[data-testid="stColumn"]:has(.reward-chip-zone) button:hover,
                        div[data-testid="column"]:has(.reward-chip-zone) button:hover {
                            background-color: #15803d !important;
                            border-color: #166534 !important;
                        }

                        /* 텍스트 줄바꿈 방지 및 가독성 최적화 */
                        div.stButton > button {
                            white-space: nowrap !important;
                        }
                        div.stButton > button *,
                        div.stButton > button p,
                        div.stButton > button span {
                            white-space: nowrap !important;
                        }
                    </style>
                    """, unsafe_allow_html=True)
                    # 1행: 상단 알림 제목
                    if danger_items or caution_items:
                        st.markdown('<div style="font-size: 15px; font-weight: 800; color: #0f172a; display: flex; align-items: center; gap: 8px;"><span class="siren-icon">🚨</span> <span class="alert-blink-badge">[과중 근무 발생 알림]</span> <span style="font-weight: 800; color: #dc2626;">선택 기간 내 주 40시간 / 52시간 초과 팀원이 감지되었습니다!</span></div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="font-size: 15px; font-weight: 800; color: #0f172a; display: flex; align-items: center; gap: 8px;"><span>🎉</span> <span style="background: #d1e7dd; color: #0f5132; border: 1px solid #a3cfbb; padding: 2px 8px; border-radius: 4px; font-weight: 800; font-size: 12px;">[과중 근무 보상 완료]</span> <span style="font-weight: 800; color: #16a34a;">초과 근무 팀원에 대한 보상 휴가 처리가 모두 완료되었습니다!</span></div>', unsafe_allow_html=True)

                    st.markdown("<div style='margin-top: 6px; margin-bottom: 10px; border-top: 1px solid #fecaca;'></div>", unsafe_allow_html=True)
                    
                    # 2행: 🚨 주 52h 초과 위험 팀원들 (있을 경우 - 빨간색 배경, 5개씩 넉넉하게 줄바꿈)
                    if danger_items:
                        col_d_lbl, col_d_chips = st.columns([1.4, 8.6])
                        with col_d_lbl:
                            st.markdown(f"<div style='padding-top:6px; font-size:13px; font-weight:800; color:#dc2626;'>🚨 주 52h 초과 ({len(danger_items)}건):</div>", unsafe_allow_html=True)
                        with col_d_chips:
                            chunk_size = 5
                            for i in range(0, len(danger_items), chunk_size):
                                chunk = danger_items[i:i + chunk_size]
                                d_cols = st.columns(chunk_size)
                                for c_idx, d_item in enumerate(chunk):
                                    with d_cols[c_idx]:
                                        if st.button(
                                            f"🚨 {d_item['worker_name']}({d_item['short_w']}:{d_item['val']}h)",
                                            key=f"btn_chip_danger_{d_item['worker_name']}_{d_item['week_label']}",
                                            type="primary",
                                            use_container_width=True
                                        ):
                                            show_weekly_detail_dialog(d_item["worker_name"], df, default_week_name=d_item["week_label"])

                    # 3행: ⚠️ 주 40h 초과 주의 팀원들 (있을 경우 - 주황색 배경, 5개씩 넉넉하게 줄바꿈)
                    if caution_items:
                        col_c_lbl, col_c_chips = st.columns([1.4, 8.6])
                        with col_c_lbl:
                            st.markdown(f"<div style='padding-top:6px; font-size:13px; font-weight:800; color:#d97706;'>⚠️ 주 40h 초과 ({len(caution_items)}건):</div>", unsafe_allow_html=True)
                        with col_c_chips:
                            chunk_size = 5
                            for i in range(0, len(caution_items), chunk_size):
                                chunk = caution_items[i:i + chunk_size]
                                c_cols = st.columns(chunk_size)
                                for c_idx, c_item in enumerate(chunk):
                                    with c_cols[c_idx]:
                                        if st.button(
                                            f"⚠️ {c_item['worker_name']}({c_item['short_w']}:{c_item['val']}h)",
                                            key=f"btn_chip_caution_{c_item['worker_name']}_{c_item['week_label']}",
                                            type="secondary",
                                            use_container_width=True
                                        ):
                                            show_weekly_detail_dialog(c_item["worker_name"], df, default_week_name=c_item["week_label"])

                    # 4행: ✅ 과중근무 보상완료 팀원들 (있을 경우 - 초록색 배경, 5개씩 넉넉하게 줄바꿈)
                    if rewarded_items:
                        col_r_lbl, col_r_chips = st.columns([1.4, 8.6])
                        with col_r_lbl:
                            st.markdown(f"<div style='padding-top:6px; font-size:13px; font-weight:800; color:#16a34a;'>✅ 보상 완료 ({len(rewarded_items)}건):</div>", unsafe_allow_html=True)
                        with col_r_chips:
                            st.markdown('<span class="reward-chip-zone" style="display:none;"></span>', unsafe_allow_html=True)
                            chunk_size = 5
                            for i in range(0, len(rewarded_items), chunk_size):
                                chunk = rewarded_items[i:i + chunk_size]
                                r_cols = st.columns(chunk_size)
                                for c_idx, r_item in enumerate(chunk):
                                    with r_cols[c_idx]:
                                        if st.button(
                                            f"✅ {r_item['worker_name']}({r_item['short_w']}:{r_item['val']}h)",
                                            key=f"btn_chip_reward_{r_item['worker_name']}_{r_item['week_label']}",
                                            use_container_width=True
                                        ):
                                            show_weekly_detail_dialog(r_item["worker_name"], df, default_week_name=r_item["week_label"])
            else:
                # 🟢 과중 근무자가 없는 경우: 일체형 카드 배너 (상단 5개 카드와 간격 28px 정밀 일치)
                st.markdown("""
                <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 6px solid #16a34a; border-radius: 8px; padding: 10px 18px; margin: 18px 0 0 0; display: flex; justify-content: space-between; align-items: center; width: 100%; box-sizing: border-box; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);">
                    <div style="font-size: 14px; font-weight: 700; color: #0f5132; display: flex; align-items: center; gap: 10px; margin: 0; padding: 0; line-height: 1;">
                        <span style="font-size: 15px; line-height: 1;">🟢</span>
                        <span style="background: #d1e7dd; color: #0f5132; border: 1px solid #a3cfbb; padding: 2px 8px; border-radius: 4px; font-weight: 800; font-size: 12px; line-height: 1.2; display: inline-flex; align-items: center;">[과중 근무 없음]</span>
                        <span style="color: #334155; font-size: 13px; line-height: 1; font-weight: 500;">현재 선택된 기간 내에 주 40시간 / 52시간을 초과한 과중 근무 팀원이 없습니다. (안정적인 근무 상태)</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        # 📌 과중 근무 배너와 회색선, 회색선과 LIVE 관제 사이 간격을 정확히 28px로 균일 배치
        st.markdown("<div style='margin-top: 28px; margin-bottom: 28px; border-top: 1.5px solid #cbd5e1;'></div>", unsafe_allow_html=True)

        # 🟢 오늘 실시간 작업 현황 라이브 보드 (첫 화면에 단독 풀사이즈 표출)
        render_today_live_board(df_raw, team_mappings, selected_team)

    elif curr_page == "📅 작업 캘린더 & 밀도 히트맵":
        render_calendar_and_heatmap_tab(df, df_raw, selected_team)

    elif curr_page == "🔍 전체 작업 스마트 검색":
        render_smart_search_tab(df_raw, team_mappings)

    elif curr_page == "📊 Summary":
        render_executive_summary_tab(df, df_raw, selected_team, team_mappings)

    elif curr_page == "👤 팀원별 업무량 분석":
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
                            name='🌙 평일 야간 (18시~06시)',
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
                            name='🌙 평일 야간 (18시~06시)',
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
    # PAGE: 팀별 업무량 비교
    # ------------------------------------------
    elif curr_page == "🏢 팀별 업무량 비교":
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
    # PAGE: 월별 / 주별 / 일별 추이 분석
    # ------------------------------------------
    elif curr_page == "📈 월별/일별 추이":
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
    # PAGE: 고객사별 공수 분포
    # ------------------------------------------
    elif curr_page == "🏢 고객사별 공수 분포":
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
    # PAGE: 예정 vs 실제 소요시간 분석
    # ------------------------------------------
    elif curr_page == "⏱️ 예정 vs 실제 소요시간":
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
