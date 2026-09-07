import os
import sys
from pathlib import Path

# WorkTime Dashboard v2.0.5 (Hide Top Leave Banner after 18:00)
APP_VERSION = "v2.0.5"

# Streamlit Cloud 및 모든 환경에서 프로젝트 루트 경로를 sys.path 최우선으로 등록
_current_file = Path(__file__).resolve()
_project_root = _current_file.parent.parent.parent  # src/dashboard/app.py -> root
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import io
import time
import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

from src.config import config
from src.database.supabase_client import db_manager
from src.services.team_service import TeamService, UNASSIGNED_TEAM
from src.services.client_normalizer import normalize_client_name
from src.auth.auth_manager import AuthManager
from src.parser.reply_matcher import check_is_night_work, check_is_weekend_work, WorkLogMatcher
from src.collector.kakao_auto_collector import (
    start_background_collector,
    get_collector_countdown_info,
    run_collection_cycle,
    WIN32_AVAILABLE
)

from src.dashboard.styles import apply_custom_styles, render_header_banner
from src.dashboard.common.ui_helpers import (
    get_bora_ntp_timestamp,
    get_all_teams_safe,
    is_same_team,
    get_month_clamped_week_label
)

from src.dashboard.views.auth_view import render_login_page
from src.dashboard.views.team_admin_view import render_team_management_page
from src.dashboard.views.worklog_view import render_worklog_view
from src.dashboard.views.home_view import render_home_view
from src.dashboard.views.calendar_view import render_calendar_view
from src.dashboard.views.search_view import render_search_view
from src.dashboard.views.summary_view import render_summary_view
from src.dashboard.views.worker_view import render_worker_view
from src.dashboard.views.team_view import render_team_view
from src.dashboard.views.trend_view import render_trend_view
from src.dashboard.views.client_view import render_client_view
from src.dashboard.views.duration_view import render_duration_view

# -------------------------------------------------------------
# 1. 단 1회 백그라운드 10분 수집 데몬 기동
# -------------------------------------------------------------
@st.cache_resource
def init_single_collector_daemon():
    """Streamlit 수명 주기 전체에서 단 1회만 백그라운드 10분 수집 데몬을 실행"""
    start_background_collector()
    return True

try:
    init_single_collector_daemon()
except Exception as e:
    print(f"[수집기 기동 알림]: {e}")

# -------------------------------------------------------------
# 2. 페이지 설정 및 Cisco 테마 CSS 주입
# -------------------------------------------------------------
st.set_page_config(
    page_title="팀 업무량 & 지원 시간 분석 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

apply_custom_styles()

def clear_all_web_caches():
    """웹 메모리 캐시, RAM 인메모리 캐시 및 서브 모듈 핫리로드(Hot-Reload) 강제 실행"""
    # 1. Streamlit 전역 캐시 초기화
    st.cache_data.clear()
    st.cache_resource.clear()
    
    # 2. TeamService RAM 캐시 초기화
    try:
        from src.services.team_service import TeamService
        TeamService.clear_cache()
    except Exception:
        pass
        
    # 3. 파이썬 서브 모듈 강제 핫리로드 (Streamlit Cloud 메모리 캐시 파괴)
    import importlib
    modules_to_reload = [
        "src.dashboard.common.ui_helpers",
        "src.services.schedule_sync_service",
        "src.dashboard.views.home_view",
        "src.dashboard.views.outlook_calendar_widget",
        "src.database.supabase_client",
        "src.services.team_service"
    ]
    for mod_name in modules_to_reload:
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                pass

# 버전 변경 시 Streamlit Cloud 및 접속 세션 캐시 자동 무효화 (최신 반영 100% 보장)
if st.session_state.get("_applied_app_version") != APP_VERSION:
    st.session_state["_applied_app_version"] = APP_VERSION
    clear_all_web_caches()

# -------------------------------------------------------------
# 3. 데이터 로딩 (멀티데이 분할 원본 중복제거, 정규화, 야간/주말 보장)
# -------------------------------------------------------------
# -------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def load_data() -> pd.DataFrame:
    df = db_manager.fetch_all_work_logs()
    if not df.empty:
        # 🛡️ 멀티데이 분할 레코드(1/3일차 등) 존재 시 분할 전 원본 레코드 자동 중복 배제 (사전 변환 최적화)
        if "task_description" in df.columns and "start_time" in df.columns and "end_time" in df.columns:
            split_mask = df["task_description"].astype(str).str.contains(r"\(\d+/\d+일차\)", regex=True)
            if split_mask.any():
                splits = df[split_mask].copy()
                splits["_st_dt"] = pd.to_datetime(splits["start_time"], errors="coerce")
                dup_origin_indices = []
                for idx, r in df[~split_mask].iterrows():
                    st_t = pd.to_datetime(r.get("start_time"), errors="coerce")
                    et_t = pd.to_datetime(r.get("end_time"), errors="coerce")
                    if pd.notna(st_t) and pd.notna(et_t) and st_t.date() != et_t.date():
                        m_splits = splits[
                            (splits["worker_name"] == r["worker_name"]) &
                            (splits["client_name"] == r["client_name"]) &
                            (splits["_st_dt"] >= st_t.floor("D")) &
                            (splits["_st_dt"] <= et_t.ceil("D"))
                        ]
                        if not m_splits.empty:
                            dup_origin_indices.append(idx)
                if dup_origin_indices:
                    df = df.drop(index=dup_origin_indices).reset_index(drop=True)

        mappings = TeamService.get_team_mappings()
        if mappings:
            df["worker_team"] = df["worker_name"].map(mappings).fillna(df["worker_team"]).fillna(UNASSIGNED_TEAM)
            
        title_mappings = TeamService.get_title_mappings()
        if title_mappings:
            df["worker_title"] = df["worker_name"].map(title_mappings).fillna(df.get("worker_title", ""))
            
        # 🏢 고객사명 대소문자/띄어쓰기 표준화 (고유값 사전 캐시 매핑으로 95% 속도 향상)
        if "client_name" in df.columns:
            unique_clients = df["client_name"].dropna().unique()
            client_map = {c: normalize_client_name(c) for c in unique_clients}
            df["client_name"] = df["client_name"].map(client_map).fillna(df["client_name"])

        # 🛡️ 의미론적 중복 작업 통합 제거 (Semantic Deduplication)
        dup_subset = ["worker_name", "start_time", "client_name", "task_description"]
        if all(c in df.columns for c in dup_subset):
            sort_cols = [c for c in ["status", "id"] if c in df.columns]
            if sort_cols:
                df = df.sort_values(by=sort_cols, ascending=[False] * len(sort_cols))
            df = df.drop_duplicates(subset=dup_subset, keep="first").reset_index(drop=True)

        # status 컬럼 안전 보장
        if "status" not in df.columns:
            df["status"] = "COMPLETED"
        else:
            df["status"] = df["status"].fillna("COMPLETED").astype(str)

        # week_str, week_label 안전 보장
        if "start_time" in df.columns:
            df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
            df["month_str"] = df["start_time"].dt.strftime("%Y-%m")
            df["date_str"] = df["start_time"].dt.strftime("%Y-%m-%d")
            
            df["week_str"] = df["start_time"].dt.strftime("%G-W%V")
            df["week_label"] = df["start_time"].apply(get_month_clamped_week_label)
        else:
            df["week_str"] = ""
            df["week_label"] = ""

        # 🌙 야간 및 🏖️ 주말 작업 필터링 벡터화 최적화 (후보군 대상에 대해서만 선별 계산)
        df["is_night_work"] = False
        df["is_weekend_work"] = False
        if "start_time" in df.columns and not df.empty:
            st_dt = pd.to_datetime(df["start_time"], errors="coerce")
            night_candidate_mask = (st_dt.dt.hour >= 18) | (st_dt.dt.hour < 6)
            weekend_candidate_mask = st_dt.dt.dayofweek >= 5

            def _eval_night(row):
                try:
                    st_val = row.get("start_time")
                    if hasattr(st_val, "to_pydatetime"):
                        st_val = st_val.to_pydatetime()
                    if getattr(st_val, "tzinfo", None) is not None:
                        st_val = st_val.replace(tzinfo=None)
                    act_m = int(row.get("actual_minutes") or 0)
                    est_m = int(row.get("estimated_minutes") or 0)
                    raw_msg = str(row.get("raw_start_message") or "") + " " + str(row.get("task_description") or "")
                    return check_is_night_work(st_val, None, raw_msg, est_m, act_m)
                except Exception:
                    return False

            def _eval_weekend(row):
                try:
                    st_val = row.get("start_time")
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

            if night_candidate_mask.any():
                df.loc[night_candidate_mask, "is_night_work"] = df[night_candidate_mask].apply(_eval_night, axis=1)
            if weekend_candidate_mask.any():
                df.loc[weekend_candidate_mask, "is_weekend_work"] = df[weekend_candidate_mask].apply(_eval_weekend, axis=1)

    return df



# -------------------------------------------------------------
# 4. 상단 대제목 헤더 & 하단 메인 본문 독립 프레임 (3분할 아키텍처)
# -------------------------------------------------------------
@st.fragment
def render_top_header_frame():
    """🏛️ Frame 2: 상단 대제목 헤더 독립 프레임 (NTP 시계 & 플랫폼 타이틀 고정)"""
    curr_page = st.session_state.get("current_page", "🏠 실시간 분석 대시보드")
    page_tag = curr_page.split(" ")[1] if " " in curr_page else curr_page
    if "_base_bora_initial_ms" not in st.session_state:
        bora_ts = get_bora_ntp_timestamp()
        st.session_state["_base_bora_initial_ms"] = int(bora_ts * 1000)
    initial_ms = st.session_state["_base_bora_initial_ms"]

    render_header_banner(initial_ms, page_tag)


@st.fragment
def render_main_content_frame(
    curr_page: str,
    df: pd.DataFrame,
    df_raw: pd.DataFrame,
    df_filtered_base: pd.DataFrame,
    selected_team: str,
    team_mappings: dict,
    all_workers_list: list,
    team_available_workers: list,
    selected_months: list,
    available_months: list,
    worker_mode: str,
    selected_workers: list,
    title_mode: str,
    selected_titles: list,
    client_mode: str,
    selected_clients: list,
    type_mode: str,
    selected_types: list,
    night_only: bool,
    weekend_only: bool,
    custom_period_desc: str = ""
):
    """🏛️ Frame 3: 하단 메인 본문 콘텐츠 독립 프레임 (12대 메뉴 뷰 라우팅 & 관제 캔버스)"""
    # 0) 🔐 로그인 페이지
    if curr_page == "🔐 시스템 로그인":
        render_login_page()
        return

    # 🔒 관리자 전용 페이지 가드
    admin_only_pages = [
        "⚙️ 팀원 소속 및 직급 관리 (팀 생성/배정)",
        "📋 작업 기록 원장 & 엑셀"
    ]
    if curr_page in admin_only_pages and not AuthManager.is_authenticated():
        st.warning("🔒 관리자 로그인이 필요한 메뉴입니다. 아래에서 먼저 로그인해주세요.")
        render_login_page()
        return

    # 1) ⚙️ 팀원 소속 및 직급 관리 (관리자)
    if curr_page == "⚙️ 팀원 소속 및 직급 관리 (팀 생성/배정)":
        render_team_management_page(all_workers_list, team_mappings)
        return

    # 2) 📋 작업 기록 원장 & 엑셀 (관리자)
    if curr_page == "📋 작업 기록 원장 & 엑셀":
        render_worklog_view(df)
        return

    # 3) 🏠 실시간 분석 대시보드 (메인)
    if custom_period_desc:
        month_desc = custom_period_desc
    elif len(selected_months) == len(available_months):
        month_desc = "전체 기간"
    else:
        month_desc = ", ".join(selected_months) if len(selected_months) <= 2 else f"{selected_months[0]} 외 {len(selected_months)-1}개 월"

    if worker_mode == "팀 전체 인원":
        if selected_team != "전체 팀":
            worker_desc = f"{selected_team} 전체 ({len(team_available_workers)}명)"
        else:
            worker_desc = f"전체 인원 ({len(all_workers_list)}명)"
    else:
        worker_desc = ", ".join(selected_workers) if len(selected_workers) <= 3 else f"{selected_workers[0]} 외 {len(selected_workers)-1}명"

    # 🎯 추가 상세 필터 활성 칩 구성
    extra_chips = []
    if title_mode != "전체 직급" and selected_titles:
        extra_chips.append(f'<div class="criteria-chip chip-extra"><span class="chip-label">👔 직급:</span><span class="chip-value">{", ".join(selected_titles)}</span></div>')
    if client_mode != "전체 고객사" and selected_clients:
        c_txt = selected_clients[0] if len(selected_clients) == 1 else f"{selected_clients[0]} 외 {len(selected_clients)-1}사"
        extra_chips.append(f'<div class="criteria-chip chip-extra"><span class="chip-label">🏢 고객사:</span><span class="chip-value">{c_txt}</span></div>')
    if type_mode != "전체 구분" and selected_types:
        t_txt = selected_types[0] if len(selected_types) == 1 else f"{selected_types[0]} 외 {len(selected_types)-1}개"
        extra_chips.append(f'<div class="criteria-chip chip-extra"><span class="chip-label">🏷️ 구분:</span><span class="chip-value">{t_txt}</span></div>')
    if night_only:
        extra_chips.append('<div class="criteria-chip chip-extra"><span class="chip-label">🌙</span><span class="chip-value">야간 전용</span></div>')
    if weekend_only:
        extra_chips.append('<div class="criteria-chip chip-extra"><span class="chip-label">🏖️</span><span class="chip-value">주말 전용</span></div>')

    extra_chips_str = "".join(extra_chips)

    # ==========================================
    # 메인 캔버스 뷰 전환 라우터 (선택된 메뉴 화면 호출)
    # ==========================================
    if curr_page == "🏠 실시간 분석 대시보드":
        render_home_view(
            df=df,
            df_raw=df_raw,
            selected_team=selected_team,
            team_mappings=team_mappings,
            month_desc=month_desc,
            worker_desc=worker_desc,
            extra_chips_str=extra_chips_str
        )
    elif curr_page == "📅 작업 캘린더 & 밀도 히트맵":
        render_calendar_view(df, df_raw, selected_team)
    elif curr_page == "🔍 전체 작업 스마트 검색":
        render_search_view(df_raw, team_mappings)
    elif curr_page == "📊 Summary":
        render_summary_view(df, df_raw, selected_team, team_mappings, month_desc=month_desc)
    elif curr_page == "👤 팀원별 업무량 분석":
        render_worker_view(df, selected_team, month_desc, df_raw=df_raw, team_mappings=team_mappings)
    elif curr_page == "🏢 팀별 업무량 비교":
        render_team_view(df_raw, selected_months, month_desc=month_desc, team_mappings=team_mappings)
    elif curr_page == "📈 월별/일별 추이":
        render_trend_view(df, df_filtered_base, selected_months, available_months, month_desc)
    elif curr_page == "🏢 고객사별 공수 분포":
        render_client_view(df)
    elif curr_page == "⏱️ 예정 vs 실제 소요시간":
        render_duration_view(df)


# -------------------------------------------------------------
# 5. 메인 오케스트레이터 (사이드바 & 프레임 통합 조율)
# -------------------------------------------------------------
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

    def set_nav_page(target_page: str):
        """사이드바 메뉴 클릭 즉시 1차 패스에서 목적지 페이지로 다이렉트 전환 (2연속 중복 Rerun 완전 제거)"""
        if st.session_state.get("current_page") != target_page:
            st.session_state["current_page"] = target_page

    # ==========================================
    # 사이드바: Cisco Catalyst Center 5대 네비게이션 드로어
    # ==========================================
    with st.sidebar:
        # 🏛️ APIC 스타일 사이드바 헤더
        st.markdown(f"""
        <div style="padding: 12px 10px 10px 10px; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: flex-start;">
            <div>
                <div style="font-size: 15px; font-weight: 800; color: #00b4d8; letter-spacing: -0.3px;">기술본부 관제센터</div>
                <div style="font-size: 10px; color: #5a8a9e; margin-top: 2px; letter-spacing: 0.5px;">FIELD SUPPORT PORTAL</div>
            </div>
            <span style="background: rgba(0, 180, 216, 0.2); color: #00b4d8; border: 1px solid rgba(0, 180, 216, 0.4); border-radius: 6px; padding: 2px 6px; font-size: 10px; font-weight: 800;">{APP_VERSION}</span>
        </div>
        """, unsafe_allow_html=True)

        # 🏠 최상단 독립 메인 버튼: 실시간 분석 대시보드 (위아래 30px 간격, on_click 콜백으로 0.1초 즉시 전환)
        st.markdown('<div style="height: 30px;"></div><span id="home-nav-marker" style="display:none;"></span>', unsafe_allow_html=True)
        is_main_active = (st.session_state.get("current_page") == "🏠 실시간 분석 대시보드")
        st.button(
            "🏠 실시간 분석 대시보드",
            key="btn_top_home_dashboard",
            type="primary" if is_main_active else "secondary",
            use_container_width=True,
            on_click=set_nav_page,
            args=("🏠 실시간 분석 대시보드",)
        )
        if st.button("🔄 최신 데이터 즉시 동기화", key="btn_quick_cache_sync", use_container_width=True, help="클릭 시 웹 캐시를 즉시 초기화하고 최신 DB 데이터를 다시 불러옵니다."):
            clear_all_web_caches()
            st.toast("🧹 최신 DB 데이터 및 일정을 즉시 동기화했습니다!", icon="✅")
            st.rerun()
        st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)

        is_auth = AuthManager.is_authenticated()

        # 1. 📂 메인 메뉴 (로그인 시에만 노출, on_click 콜백 즉시 전환)
        if is_auth:
            is_admin_active = (st.session_state.get("current_page") in ["⚙️ 팀원 소속 및 직급 관리 (팀 생성/배정)", "📋 작업 기록 원장 & 엑셀"])
            with st.expander("⚙ 관리", expanded=is_admin_active):
                main_menu_items = [
                    "⚙️ 팀원 소속 및 직급 관리 (팀 생성/배정)",
                    "📋 작업 기록 원장 & 엑셀"
                ]
                for m_item in main_menu_items:
                    is_active = (st.session_state["current_page"] == m_item)
                    btn_prefix = "▸ " if is_active else "  "
                    st.button(
                        f"{btn_prefix}{m_item}",
                        key=f"nav_main_{m_item}",
                        use_container_width=True,
                        type="primary" if is_active else "secondary",
                        on_click=set_nav_page,
                        args=(m_item,)
                    )

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
            custom_period_desc = ""
            if month_mode == "전체 기간":
                selected_months = available_months
                custom_period_desc = "전체 기간"
            elif month_mode == "특정 월 선택 (기본)":
                # 💡 DB에 존재하는 연도별 'YYYY년 전체' 옵션을 드롭다운 맨 아래에 배치 (예: '2026년 전체')
                years_in_data = sorted(list(set(str(m).split('-')[0] for m in available_months if '-' in str(m))), reverse=True)
                year_all_options = [f"{y}년 전체" for y in years_in_data]
                single_month_options = available_months + year_all_options

                single_month = st.selectbox(
                    "조회할 월:",
                    options=single_month_options,
                    index=0,
                    label_visibility="collapsed",
                    key="sb_filter_single_month"
                )
                if single_month and "년 전체" in single_month:
                    target_year = single_month.replace("년 전체", "").strip()
                    selected_months = [m for m in available_months if str(m).startswith(target_year)]
                    custom_period_desc = single_month
                else:
                    selected_months = [single_month] if single_month else available_months
                    custom_period_desc = ""
            else:
                selected_months = st.multiselect(
                    "조회할 월(다중):",
                    options=available_months,
                    default=available_months,
                    label_visibility="collapsed",
                    key="sb_filter_multi_months"
                )
                custom_period_desc = ""

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
            
            # 🚀 월 필터 적용 전 베이스셋 (팀, 담당자, 고객사, 작업구분, 직급, 야간/주말 필터 적용)
            df_filtered_base = df.copy()
            if selected_team != "전체 팀":
                df_filtered_base = df_filtered_base[df_filtered_base["worker_name"].isin(team_available_workers)]

            if selected_workers:
                df_filtered_base = df_filtered_base[df_filtered_base["worker_name"].isin(selected_workers)]
            else:
                df_filtered_base = df_filtered_base.iloc[0:0]

            if selected_clients:
                df_filtered_base = df_filtered_base[df_filtered_base["client_name"].isin(selected_clients)]
            else:
                df_filtered_base = df_filtered_base.iloc[0:0]

            if selected_types:
                df_filtered_base = df_filtered_base[df_filtered_base["log_type"].isin(selected_types)]
            else:
                df_filtered_base = df_filtered_base.iloc[0:0]

            # 직급 필터링 적용
            if title_mode != "전체 직급":
                df_filtered_base = df_filtered_base[df_filtered_base["worker_title"].isin(selected_titles)]

            if night_only:
                df_filtered_base = df_filtered_base[df_filtered_base["is_night_work"] == True]
            if weekend_only:
                df_filtered_base = df_filtered_base[df_filtered_base["is_weekend_work"] == True]

            # 최종 선택된 월 필터링
            if selected_months:
                df = df_filtered_base[df_filtered_base["month_str"].isin(selected_months)]
            else:
                df = df_filtered_base.iloc[0:0]


        # 3. 📊 작업 디테일 (7대 세부 분석 화면 전환)
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
        is_detail_active = (st.session_state.get("current_page") in detail_menu_items)
        with st.expander("📊 분석", expanded=is_detail_active):
            for d_item in detail_menu_items:
                is_active = (st.session_state["current_page"] == d_item)
                btn_prefix = "▸ " if is_active else "  "
                st.button(
                    f"{btn_prefix}{d_item}",
                    key=f"nav_detail_{d_item}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                    on_click=set_nav_page,
                    args=(d_item,)
                )

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
                            st.rerun()
                        elif res.get("status") == "window_not_found":
                            if sys.platform != "win32" or not WIN32_AVAILABLE:
                                st.toast("☁️ 클라우드 웹에서는 로컬 PC 카톡 창을 직접 긁어올 수 없습니다.", icon="ℹ️")
                                st.info(
                                    "ℹ️ **현재 접속하신 곳은 인터넷 클라우드 서버(worktimes.streamlit.app)입니다.**\n\n"
                                    "클라우드 웹 서버는 보안 및 환경상 사용자 PC 화면의 카카오톡 창에 직접 접근할 수 없습니다.\n\n"
                                    "💡 **데이터 동기화 방법**:\n"
                                    "1. 카카오톡이 켜져 있는 로컬 PC에서 **`update_and_run.bat`** (또는 `setup_and_run.bat`)을 실행해두시면 10분마다 자동으로 최신 대화가 클라우드 DB로 전송됩니다.\n"
                                    "2. 전송된 데이터는 아래 **`🔄 실시간 Cloud DB 새로고침`** 버튼을 누르시면 즉시 반영됩니다!"
                                )
                            else:
                                st.toast("⚠️ 카카오톡 대화방 창을 찾을 수 없습니다.", icon="❌")
                                st.error("⚠️ '🚩✨[기술본부] 업무공유방' 창을 찾을 수 없습니다.\n\n💡 **PC 카카오톡에서 해당 대화방 창을 열어둔 상태**에서 다시 눌러주세요!")
                        elif res.get("status") == "no_text":
                            st.warning("⚠️ 대화창에서 텍스트를 읽지 못했습니다. 카톡 대화방을 마우스로 한 번 클릭한 뒤 다시 눌러주세요.")
                        else:
                            st.info(f"💡 {res.get('message', '수집 완료')}")
                            st.cache_data.clear()
                            st.rerun()

                if st.button("🔄 실시간 Cloud DB 새로고침", key="btn_refresh_cloud_db", use_container_width=True):
                    st.cache_data.clear()
                    st.toast("☁️ 최신 클라우드 데이터를 불러왔습니다!", icon="✅")
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
                        clear_all_web_caches()
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
            st.button(
                "🔑 Login",
                key="btn_sidebar_standalone_login",
                type="primary" if is_login_active else "secondary",
                use_container_width=True,
                on_click=set_nav_page,
                args=("🔐 시스템 로그인",)
            )
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
    # 🏛️ Frame 2: 상단 대제목 헤더 독립 프레임 (NTP 시계 & 관제센터 타이틀 고정)
    # ==========================================
    render_top_header_frame()

    # ==========================================
    # 🏛️ Frame 3: 하단 메인 본문 콘텐츠 독립 프레임 (12대 메뉴 뷰 라우팅 & 관제 캔버스)
    # ==========================================
    curr_page = st.session_state.get("current_page", "🏠 실시간 분석 대시보드")
    render_main_content_frame(
        curr_page=curr_page,
        df=df,
        df_raw=df_raw,
        df_filtered_base=df_filtered_base,
        selected_team=selected_team,
        team_mappings=team_mappings,
        all_workers_list=all_workers_list,
        team_available_workers=team_available_workers,
        selected_months=selected_months,
        available_months=available_months,
        worker_mode=worker_mode,
        selected_workers=selected_workers,
        title_mode=title_mode,
        selected_titles=selected_titles,
        client_mode=client_mode,
        selected_clients=selected_clients,
        type_mode=type_mode,
        selected_types=selected_types,
        night_only=night_only,
        weekend_only=weekend_only,
        custom_period_desc=custom_period_desc
    )


if __name__ == "__main__":
    main()
