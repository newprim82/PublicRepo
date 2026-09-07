import re
import socket
import struct
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import pandas as pd
import streamlit as st

from ...config import config
from ...services.team_service import TeamService

KST = timezone(timedelta(hours=9))
KST_TIMEZONE = KST

def is_same_team(t1: str, t2: str) -> bool:
    """팀명 일치 여부를 유연하게 판정 (예: '기술 1팀' == '기술1팀')"""
    if not t1 or not t2:
        return False
    clean1 = str(t1).replace(" ", "").lower().strip()
    clean2 = str(t2).replace(" ", "").lower().strip()
    return clean1 == clean2

def get_current_kst_time() -> datetime:
    """한국 표준시(KST, UTC+9) 현재 시각 반환"""
    return datetime.now(KST_TIMEZONE)

_ntp_offset: Optional[float] = None
_ntp_last_sync: float = 0.0

def get_bora_ntp_timestamp() -> float:
    """time.bora.net (LGU+ 타임서버) NTP 기준 한국 표준시 타임스탬프(초) 반환 (1시간 캐싱 오프셋 적용으로 0ms 즉시 응답)"""
    global _ntp_offset, _ntp_last_sync
    now = time.time()
    if _ntp_offset is None or (now - _ntp_last_sync > 3600):
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(0.6)
            data = b'\x1b' + 47 * b'\0'
            client.sendto(data, ('time.bora.net', 123))
            resp, _ = client.recvfrom(1024)
            if resp:
                t = struct.unpack('!12I', resp)[10] - 2208988800
                _ntp_offset = float(t) - now
                _ntp_last_sync = now
        except Exception:
            if _ntp_offset is None:
                _ntp_offset = 0.0
    return now + (_ntp_offset or 0.0)

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
from src.services.email_sender import EmailSender
from src.services.client_normalizer import normalize_client_name
from src.analytics.stats_service import StatsService
from src.collector.kakao_auto_collector import start_background_collector, run_collection_cycle, get_collector_countdown_info, COLLECTOR_STATUS



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
    /* ⚡ 모달 팝업 및 뒷배경 페이드 애니메이션 완전 제거 */
    div[data-baseweb="backdrop"],
    div[data-testid="stDialog"],
    div[data-testid="stDialog"] > div,
    div[role="dialog"],
    div[role="dialog"] > div,
    div[data-baseweb="modal"],
    div[data-baseweb="modal"] > div {
        transition: none !important;
        transition-duration: 0s !important;
        transition-delay: 0s !important;
        animation: none !important;
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transform: none !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ==========================================
# 팝업 대화상자 (모달 다이얼로그) - 최상단 전역 정의
# ==========================================


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



LIVE_PROGRESS_ANIMATION_AND_TIMER = """
<style>
.live-progress-bar {
    border-radius: 5px !important;
    position: absolute !important;
    left: 0 !important;
    top: 0 !important;
    bottom: 0 !important;
    overflow: hidden !important;
}
.live-progress-bar::after {
    content: '' !important;
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    bottom: 0 !important;
    width: 100% !important;
    background: linear-gradient(
        90deg,
        rgba(255, 255, 255, 0) 0%,
        rgba(255, 255, 255, 0.35) 50%,
        rgba(255, 255, 255, 0) 100%
    ) !important;
    animation: liveShimmerFlow 2.2s infinite linear !important;
    pointer-events: none !important;
}
@keyframes liveShimmerFlow {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(100%); }
}
</style>
"""


def get_live_task_card_html(r, title_mappings, kst_now_naive, is_single_view: bool = False) -> str:
    """실시간 진행 중 작업 카드 HTML 생성 (부드러운 애니메이션 및 1분 타이머 데이터 태깅)"""
    w_name = r["worker_name"]
    w_title = title_mappings.get(w_name) or r.get("worker_title") or ""
    title_str = get_job_title_badge(w_title)
    c_name = r["client_name"]
    t_desc = r["task_description"]
    st_dt = r["start_time"]

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
    pct_display = f"{raw_pct}%"

    time_str = st_dt.strftime("%H:%M") if pd.notna(st_dt) else "시각 미상"
    st_dt_iso = st_dt.strftime("%Y-%m-%dT%H:%M:%S") if pd.notna(st_dt) else ""

    is_night_flag = bool(r.get("is_night_work"))
    if pd.notna(st_dt) and (6 <= st_dt.hour < 18):
        is_night_flag = False
    night_badge = "<span style='background:#fee2e2; color:#dc2626; padding:1px 5px; border-radius:4px; font-size:10px; font-weight:700; margin-left:3px;'>🌙 야간</span>" if is_night_flag else ""
    weekend_badge = "<span style='background:#fef3c7; color:#d97706; padding:1px 5px; border-radius:4px; font-size:10px; font-weight:700; margin-left:3px;'>🏖️ 주말</span>" if r.get("is_weekend_work") else ""

    rank_color = get_job_title_color(w_title)
    border_color = rank_color

    card_padding = "10px 12px; margin-bottom: 8px;" if is_single_view else "10px 11px; margin-bottom: 9px;"
    time_badge_label = f"시작 보고 시간 : {time_str}" if is_single_view else f"시작 {time_str}"
    client_font_size = "13px" if is_single_view else "12.5px"
    time_badge_padding = "2px 8px" if is_single_view else "1.5px 6px"

    elapsed_html = f"⏱️ 경과: <b>{elapsed_hours}h</b> ({elapsed_mins}분) {'⚠️ 초과' if is_overtime else ''}" if is_single_view else f"⏱️ 경과 {elapsed_hours}h ({elapsed_mins}분) {'⚠️' if is_overtime else ''}"
    elapsed_color = "#dc2626; font-weight:700;" if is_overtime else "#0f5132;"

    return f"""<div class="live-task-card" data-start="{st_dt_iso}" data-est="{est_hours}" data-single-view="{'true' if is_single_view else 'false'}" style="background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid {border_color}; border-radius: 8px; padding: {card_padding}; box-shadow: 0 1px 3px rgba(0,0,0,0.05);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;"><div><span style="font-size: 13.5px; font-weight: 700; color: #0f172a;">👤 {w_name}{title_str}</span>{night_badge}{weekend_badge}</div><span style="background-color: #d1e7dd; color: #0f5132; border: 1px solid #a3cfbb; border-radius: 6px; padding: {time_badge_padding}; font-size: 10.5px; font-weight: 700; white-space: nowrap;">{time_badge_label}</span></div><div style="font-size: {client_font_size}; color: #005073; font-weight: 700; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">🏢 {c_name}</div><div style="position: relative; overflow: hidden; background: #e9ecef; border-radius: 6px; border: {bar_border}; margin-bottom: 5px; min-height: 28px; display: flex; align-items: center;"><div class="live-progress-bar live-progress-fill" style="position: absolute; left: 0; top: 0; bottom: 0; width: {bar_width_pct}%; background: {bar_bg}; border-radius: 5px; transition: width 0.8s ease-in-out;\"></div><div style="position: relative; z-index: 2; width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 3px 6px; font-size: 11px; font-weight: 600; color: #ffffff; text-shadow: 0 1px 2px rgba(0,0,0,0.6); gap: 4px;"><span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 70%;">{t_desc}</span><span class="live-pct-badge" style="font-weight: 700; color: #ffffff; font-size: 10px; white-space: nowrap; background: rgba(0,0,0,0.4); padding: 1px 3px; border-radius: 4px;">{pct_display}</span></div></div><div style="display: flex; justify-content: space-between; font-size: 10.5px; color: #64748b; margin-top: 2px;"><span>⏱️ 예정 {est_hours}h</span><span class="live-elapsed-time" style="color: {elapsed_color}">{elapsed_html}</span></div></div>"""
def get_team_theme(team_name: str) -> dict:
    """팀별 고유 아이덴티티 컬러, 아이콘, 틴트 배경 그라데이션 반환 (식별성 극대화)"""
    t = str(team_name).strip()
    if "본부" in t:
        return {
            "icon": "🏛️",
            "primary": "#1e3a8a",
            "border": "#bfdbfe",
            "bg_gradient": "linear-gradient(90deg, #eff6ff 0%, #f8fafc 100%)",
            "text_color": "#0f172a",
            "tag": "본부",
        }
    elif "1팀" in t:
        return {
            "icon": "🌐",
            "primary": "#0284c7",
            "border": "#bae6fd",
            "bg_gradient": "linear-gradient(90deg, #f0f9ff 0%, #f8fafc 100%)",
            "text_color": "#0f172a",
            "tag": "1팀",
        }
    elif "2팀" in t:
        return {
            "icon": "🌿",
            "primary": "#059669",
            "border": "#a7f3d0",
            "bg_gradient": "linear-gradient(90deg, #ecfdf5 0%, #f8fafc 100%)",
            "text_color": "#0f172a",
            "tag": "2팀",
        }
    elif "3팀" in t:
        return {
            "icon": "🍇",
            "primary": "#7c3aed",
            "border": "#ddd6fe",
            "bg_gradient": "linear-gradient(90deg, #f5f3ff 0%, #f8fafc 100%)",
            "text_color": "#0f172a",
            "tag": "3팀",
        }
    elif "PI" in t.upper() or "파이" in t:
        return {
            "icon": "⚡",
            "primary": "#d97706",
            "border": "#fde68a",
            "bg_gradient": "linear-gradient(90deg, #fffbeb 0%, #f8fafc 100%)",
            "text_color": "#0f172a",
            "tag": "PI팀",
        }
    else:
        return {
            "icon": "🏢",
            "primary": "#64748b",
            "border": "#cbd5e1",
            "bg_gradient": "linear-gradient(90deg, #f1f5f9 0%, #f8fafc 100%)",
            "text_color": "#0f172a",
            "tag": "기타",
        }

