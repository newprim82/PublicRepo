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

def get_current_kst_time() -> datetime:
    """time.bora.net (LGU+ 타임서버) NTP 기준 한국 표준시(KST, UTC+9) 현재 시각 반환 (상단 헤더 프레임 시계와 100% 일치)"""
    ts = get_bora_ntp_timestamp()
    return datetime.fromtimestamp(ts, tz=KST_TIMEZONE)

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

    /* ⚠️ 모달 내부 노란색 경고창 배경 및 테두리 강제 적용 */
    .overwork-warning-box,
    div.overwork-warning-box {
        background: #fef08a !important;
        background-color: #fef08a !important;
        border: 1.5px solid #facc15 !important;
        border-left: 6px solid #ca8a04 !important;
        border-radius: 8px !important;
        padding: 13px 18px !important;
        margin-bottom: 14px !important;
        display: block !important;
    }

    /* 🚨 모달 내부 빨간색 경고창 배경 및 테두리 강제 적용 */
    .overwork-danger-box,
    div.overwork-danger-box {
        background: #fee2e2 !important;
        background-color: #fee2e2 !important;
        border: 1.5px solid #f87171 !important;
        border-left: 6px solid #ef4444 !important;
        border-radius: 8px !important;
        padding: 13px 18px !important;
        margin-bottom: 14px !important;
        display: block !important;
    }

    /* ⚠️ 모달 내부 노란색/경고/알림창 글자색 완전 블랙 고대비 보장 (흰색 글씨 원천 차단) */
    .overwork-warning-box,
    .overwork-warning-box *,
    div.overwork-warning-box *,
    div[data-testid="stDialog"] .overwork-warning-box *,
    div[role="dialog"] .overwork-warning-box *,
    div[data-baseweb="modal"] .overwork-warning-box *,
    div[data-testid="stDialog"] div[data-testid="stAlert"] *,
    div[role="dialog"] div[data-testid="stAlert"] *,
    div[data-baseweb="modal"] div[data-testid="stAlert"] *,
    div[data-testid="stDialog"] div[style*="fef08a"] *,
    div[data-testid="stDialog"] div[style*="fefce8"] *,
    div[data-testid="stDialog"] div[style*="fffbeb"] *,
    div[data-testid="stDialog"] div[style*="fde047"] *,
    div[role="dialog"] div[style*="fef08a"] *,
    div[role="dialog"] div[style*="fefce8"] *,
    div[data-baseweb="modal"] div[style*="fef08a"] * {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        font-weight: 800 !important;
        text-shadow: none !important;
    }

    /* 🚨 모달 내부 빨간색 경고창 글자색 보장 */
    .overwork-danger-box,
    .overwork-danger-box *,
    div.overwork-danger-box *,
    div[data-testid="stDialog"] .overwork-danger-box *,
    div[role="dialog"] .overwork-danger-box *,
    div[data-testid="stDialog"] div[style*="fecaca"] *,
    div[data-testid="stDialog"] div[style*="fef2f2"] * {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        font-weight: 800 !important;
        text-shadow: none !important;
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

    is_outlook = bool(r.get("is_outlook"))
    outlook_badge = "<span style='background:#e0f2fe; color:#0369a1; padding:1px 5px; border-radius:4px; font-size:10px; font-weight:700; margin-left:3px;'>📅 일정표</span>" if is_outlook else ""

    if is_outlook and "outlook_progress_pct" in r:
        raw_pct = int(r["outlook_progress_pct"])
        est_hours = float(r.get("total_hours") or r.get("estimated_hours") or 0)
    else:
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
    time_badge_label = f"일정 시작 : {time_str}" if is_outlook else (f"시작 보고 시간 : {time_str}" if is_single_view else f"시작 {time_str}")
    client_font_size = "13px" if is_single_view else "12.5px"
    time_badge_padding = "2px 8px" if is_single_view else "1.5px 6px"

    elapsed_html = f"⏱️ 경과: <b>{elapsed_hours}h</b> ({elapsed_mins}분) {'⚠️ 초과' if is_overtime else ''}" if is_single_view else f"⏱️ 경과 {elapsed_hours}h ({elapsed_mins}분) {'⚠️' if is_overtime else ''}"
    elapsed_color = "#dc2626; font-weight:700;" if is_overtime else "#0f5132;"

    return f"""<div class="live-task-card" data-start="{st_dt_iso}" data-est="{est_hours}" data-single-view="{'true' if is_single_view else 'false'}" style="background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid {border_color}; border-radius: 8px; padding: {card_padding}; box-shadow: 0 1px 3px rgba(0,0,0,0.05);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;"><div><span style="font-size: 13.5px; font-weight: 700; color: #0f172a;">👤 {w_name}{title_str}</span>{night_badge}{weekend_badge}{outlook_badge}</div><span style="background-color: #d1e7dd; color: #0f5132; border: 1px solid #a3cfbb; border-radius: 6px; padding: {time_badge_padding}; font-size: 10.5px; font-weight: 700; white-space: nowrap;">{time_badge_label}</span></div><div style="font-size: {client_font_size}; color: #005073; font-weight: 700; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">🏢 {c_name}</div><div style="position: relative; overflow: hidden; background: #e9ecef; border-radius: 6px; border: {bar_border}; margin-bottom: 5px; min-height: 28px; display: flex; align-items: center;"><div class="live-progress-bar live-progress-fill" style="position: absolute; left: 0; top: 0; bottom: 0; width: {bar_width_pct}%; background: {bar_bg}; border-radius: 5px; transition: width 0.8s ease-in-out;\"></div><div style="position: relative; z-index: 2; width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 3px 6px; font-size: 11px; font-weight: 600; color: #ffffff; text-shadow: 0 1px 2px rgba(0,0,0,0.6); gap: 4px;"><span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 70%;">{t_desc}</span><span class="live-pct-badge" style="font-weight: 700; color: #ffffff; font-size: 10px; white-space: nowrap; background: rgba(0,0,0,0.4); padding: 1px 3px; border-radius: 4px;">{pct_display}</span></div></div><div style="display: flex; justify-content: space-between; font-size: 10.5px; color: #64748b; margin-top: 2px;"><span>⏱️ 예정 {est_hours}h</span><span class="live-elapsed-time" style="color: {elapsed_color}">{elapsed_html}</span></div></div>"""


def get_leave_card_html(r: dict, is_single_view: bool = False) -> str:
    """휴가/연차/반차 전용 100% 완료 상태 카드 HTML"""
    w_name = r["worker_name"]
    leave_type = r.get("leave_type") or "연차"
    subj = r.get("subject") or f"{w_name} {leave_type}"
    dur_h = r.get("duration_hours", 9.0)
    st_t = r["start_time"].strftime("%H:%M") if hasattr(r["start_time"], "strftime") else "09:00"
    ed_t = r["end_time"].strftime("%H:%M") if hasattr(r["end_time"], "strftime") else "18:00"

    card_pad = "10px 12px; margin-bottom: 8px;" if is_single_view else "10px 11px; margin-bottom: 9px;"
    return f"""<div style="background: #faf5ff; border: 1px solid #e9d5ff; border-left: 4px solid #a855f7; border-radius: 8px; padding: {card_pad}; box-shadow: 0 1px 3px rgba(168,85,247,0.06);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;"><div><span style="font-size: 13.5px; font-weight: 700; color: #581c87;">👤 {w_name}</span><span style="background: #f3e8ff; color: #7e22ce; border: 1px solid #d8b4fe; padding: 1px 6px; border-radius: 4px; font-size: 10.5px; font-weight: 800; margin-left: 4px;">🏖️ {leave_type}</span></div><span style="background: #f3e8ff; color: #7e22ce; border-radius: 6px; padding: 1.5px 6px; font-size: 10.5px; font-weight: 700;">{st_t}~{ed_t}</span></div><div style="position: relative; overflow: hidden; background: #e9d5ff; border-radius: 6px; margin-bottom: 5px; min-height: 28px; display: flex; align-items: center;"><div style="position: absolute; left: 0; top: 0; bottom: 0; width: 100%; background: linear-gradient(90deg, #9333ea 0%, #a855f7 100%); border-radius: 5px;"></div><div style="position: relative; z-index: 2; width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 3px 8px; font-size: 11px; font-weight: 700; color: #ffffff; text-shadow: 0 1px 2px rgba(0,0,0,0.5);"><span>{subj}</span><span style="background: rgba(0,0,0,0.3); padding: 1px 5px; border-radius: 4px;">100% 완료</span></div></div><div style="display: flex; justify-content: space-between; font-size: 10.5px; color: #7e22ce; font-weight: 600;"><span>⏱️ 휴가 인정: {dur_h}h</span><span>부여 완료 상태</span></div></div>"""
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


def get_month_clamped_week_label(dt) -> str:
    """월 경계를 넘지 않고 해당 월(1일~말일) 안에서만 월요일~일요일 단위로 주차를 분할하는 라벨 생성 함수.
    
    규칙:
    - 1주차: 1일부터 1일이 속한 주의 일요일까지 (예: 2026-08-01 토 ~ 2026-08-02 일 -> 2026-08 1주차 (08/01~08/02))
    - 2주차 이후: 매주 월요일부터 일요일까지 (예: 2026-08 2주차 (08/03~08/09), 3주차 (08/10~08/16)...)
    - 마지막 주차: 마지막 주 월요일부터 해당 월의 말일까지 (예: 2026-08 6주차 (08/31~08/31))
    - 인접 월(전달, 다음달) 날짜가 절대 섞이지 않음.
    """
    if pd.isna(dt):
        return ""
    if hasattr(dt, "to_pydatetime"):
        dt = dt.to_pydatetime()
    
    import calendar
    from datetime import date, timedelta

    y = dt.year
    m = dt.month
    d = dt.day
    target_date = date(y, m, d)
    
    last_day_num = calendar.monthrange(y, m)[1]
    cur_start = date(y, m, 1)
    week_num = 1
    
    while cur_start.day <= last_day_num:
        days_to_sun = 6 - cur_start.weekday()
        cur_sun = cur_start + timedelta(days=days_to_sun)
        cur_end = min(cur_sun, date(y, m, last_day_num))
        
        if cur_start <= target_date <= cur_end:
            return f"{y:04d}-{m:02d} {week_num}주차 ({cur_start.strftime('%m/%d')}~{cur_end.strftime('%m/%d')})"
        
        cur_start = cur_end + timedelta(days=1)
        week_num += 1
        if cur_start.month != m:
            break
            
    return ""


def extract_week_sort_key(w_lbl: str) -> list:
    """주차 라벨에서 정렬을 위한 숫자 리스트 추출 (예: '2026-08 1주차 (08/01~08/02)' -> [2026, 8, 1, 8, 1, 8, 2])"""
    import re
    nums = [int(n) for n in re.findall(r'\d+', str(w_lbl))]
    return nums if nums else [9999]


def get_all_weeks_for_month(year: int, month: int) -> list:
    """해당 월의 1일부터 말일까지의 주차 중 오늘 기준 이미 시작된 주차 라벨만 순서대로 반환 (아직 시작되지 않은 미래 주차 제외)"""
    import calendar
    from datetime import date, timedelta
    
    try:
        today = get_current_kst_time().date()
    except Exception:
        today = date.today()
        
    last_day_num = calendar.monthrange(year, month)[1]
    cur_start = date(year, month, 1)
    week_num = 1
    weeks = []
    while cur_start.day <= last_day_num:
        # 💡 아직 시작되지 않은 주차(시작일이 오늘보다 미래)는 생성하지 않음
        if cur_start > today:
            break
            
        days_to_sun = 6 - cur_start.weekday()
        cur_sun = cur_start + timedelta(days=days_to_sun)
        cur_end = min(cur_sun, date(year, month, last_day_num))
        lbl = f"{year:04d}-{month:02d} {week_num}주차 ({cur_start.strftime('%m/%d')}~{cur_end.strftime('%m/%d')})"
        weeks.append(lbl)
        cur_start = cur_end + timedelta(days=1)
        week_num += 1
        if cur_start.month != month:
            break
    return weeks


def get_available_weeks_for_df(df_scope: pd.DataFrame, month_desc: str = "") -> list:
    """선택된 월(들)에 대해 오늘 기준 이미 시작된 주차 목록을 누락 없이 반환 (아직 시작되지 않은 미래 주차 제외)"""
    import re
    months = []
    # 1. month_desc에서 YYYY-MM 패턴 추출 또는 YYYY년 전체 지원
    if month_desc:
        if "년 전체" in str(month_desc):
            y_match = re.search(r'\b(20\d\d)년', str(month_desc))
            if y_match:
                y_val = int(y_match.group(1))
                for m_num in range(1, 13):
                    m_str = f"{y_val}-{m_num:02d}"
                    if m_str not in months:
                        months.append(m_str)
        else:
            found = re.findall(r'\b(20\d\d[-/]\d{1,2})\b', str(month_desc))
            for m in found:
                clean_m = m.replace('/', '-')
                parts = clean_m.split('-')
                clean_m = f"{parts[0]}-{int(parts[1]):02d}"
                if clean_m not in months:
                    months.append(clean_m)
    
    # 2. df_scope에서 월 추출
    if not months and df_scope is not None and not df_scope.empty:
        if "month_str" in df_scope.columns:
            months = [m for m in df_scope["month_str"].dropna().unique() if str(m).strip()]
        elif "start_time" in df_scope.columns:
            st_col = pd.to_datetime(df_scope["start_time"], errors="coerce").dropna()
            if not st_col.empty:
                months = list(st_col.dt.strftime("%Y-%m").unique())

    all_weeks = []
    for m_str in sorted(months):
        try:
            parts = m_str.split('-')
            y, m = int(parts[0]), int(parts[1])
            w_list = get_all_weeks_for_month(y, m)
            for w in w_list:
                if w not in all_weeks:
                    all_weeks.append(w)
        except Exception:
            pass

    # 만약 위에서 못 구했으면 df_scope에 존재하는 주차들 사용
    if not all_weeks and df_scope is not None and not df_scope.empty and "week_label" in df_scope.columns:
        all_weeks = [w for w in df_scope["week_label"].dropna().unique() if str(w).strip()]

    # 💡 오늘 기준 아직 시작되지 않은 미래 주차(시작일 > 오늘)는 안전하게 2차 필터링
    try:
        today = get_current_kst_time().date()
    except Exception:
        from datetime import date
        today = date.today()

    filtered_weeks = []
    for w in all_weeks:
        w_info = get_week_label_info(w)
        if w_info.get("start_date"):
            if w_info["start_date"] <= today:
                filtered_weeks.append(w)
        else:
            filtered_weeks.append(w)

    return sorted(filtered_weeks, key=extract_week_sort_key)


def get_week_label_info(week_label: str) -> dict:
    """주차 라벨(예: '2026-08 1주차 (08/01~08/02)')에서 기간 정보를 파싱하고 주말(토/일)만으로 이루어진 주차인지 판별"""
    import re
    from datetime import date, timedelta
    
    res = {
        "year": None,
        "month": None,
        "week_num": None,
        "is_weekend_only": False,
        "start_date": None,
        "end_date": None
    }
    
    if not week_label:
        return res
        
    m = re.search(r'(\d{4})-(\d{2})\s+(\d+)주차\s+\((\d{2})/(\d{2})~(\d{2})/(\d{2})\)', str(week_label))
    if m:
        y, mo, w_num, sm, sd, em, ed = m.groups()
        try:
            s_date = date(int(y), int(sm), int(sd))
            e_date = date(int(y), int(em), int(ed))
            res["year"] = int(y)
            res["month"] = int(mo)
            res["week_num"] = int(w_num)
            res["start_date"] = s_date
            res["end_date"] = e_date
            
            # 기간 내 모든 날짜가 토(5) 또는 일(6)인지 검사
            cur = s_date
            all_weekend = True
            while cur <= e_date:
                if cur.weekday() < 5:  # 0~4는 평일(월~금)
                    all_weekend = False
                    break
                cur += timedelta(days=1)
            res["is_weekend_only"] = all_weekend
        except Exception:
            pass
    return res


def render_empty_week_notice(week_label: str, team_name: str = "전체"):
    """작업 데이터가 없는 주차 선택 시, 주말만 있는 기간 여부 및 카카오톡 원장 기록 없음 안내 배너 렌더링"""
    info = get_week_label_info(week_label)
    is_weekend = info.get("is_weekend_only", False)
    
    team_clean = str(team_name).strip()
    team_str = f"선택하신 <b>[{team_clean}]</b>의 " if team_clean and team_clean not in ["전체", "전체 팀", "전체팀"] else ""
    
    if is_weekend:
        html = f"""
        <div style="background: #fffbeb; border: 1.5px solid #fef3c7; border-left: 5.5px solid #f59e0b; border-radius: 8px; padding: 16px 20px; margin: 12px 0 20px 0; box-shadow: 0 2px 6px rgba(0,0,0,0.04);">
            <div style="font-size: 15px; font-weight: 800; color: #92400e; margin-bottom: 6px; display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 18px;">ℹ️</span>
                <span style="color: #92400e !important; font-weight: 800 !important;">해당 주차({week_label})는 <strong>주말(토·일)만 포함된 기간</strong>입니다.</span>
            </div>
            <div style="font-size: 13.5px; color: #78350f !important; line-height: 1.6;">
                <span style="color: #78350f !important; font-weight: 600;">{team_str}해당 기간 동안 <strong style="color: #451a03 !important;">카카오톡 원장 기록이 없습니다.</strong></span><br>
                <span style="color: #b45309 !important; font-size: 12.5px; font-weight: 600;">※ 주말에 공식 작업 내역이 없거나 카카오톡 대화방에 시작/완료 보고가 등록되지 않은 경우 정상적으로 데이터가 집계되지 않습니다.</span>
            </div>
        </div>
        """
    else:
        html = f"""
        <div style="background: #f8fafc; border: 1.5px solid #e2e8f0; border-left: 5.5px solid #64748b; border-radius: 8px; padding: 16px 20px; margin: 12px 0 20px 0; box-shadow: 0 2px 6px rgba(0,0,0,0.04);">
            <div style="font-size: 15px; font-weight: 800; color: #1e293b; margin-bottom: 6px; display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 18px;">📋</span>
                <span style="color: #1e293b !important; font-weight: 800 !important;">해당 주차({week_label})는 <strong>카카오톡 원장 기록이 없습니다.</strong></span>
            </div>
            <div style="font-size: 13.5px; color: #334155 !important; line-height: 1.6;">
                {team_str}해당 기간 동안 카카오톡 대화방에 등록된 시작/완료 작업 내역이 존재하지 않습니다.
            </div>
        </div>
        """
    st.markdown(html, unsafe_allow_html=True)




