import io
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from ...services.cost_estimation_service import CostEstimationService
from ...services.excel_export_service import ExcelExportService
from ...services.team_service import TeamService, UNASSIGNED_TEAM
from ...auth.auth_manager import AuthManager
from ..common.ui_helpers import (
    get_job_title_badge,
    get_job_title_color,
    get_job_title_rank,
    get_available_weeks_for_df,
    is_same_team
)


def render_cost_estimation_view(
    df: pd.DataFrame,
    df_raw: pd.DataFrame,
    selected_team: str,
    team_mappings: dict,
    month_desc: str = "",
    worker_desc: str = "",
    extra_chips_str: str = "",
    curr_page: str = "💰 예상 비용산정",
    df_filtered_base: Optional[pd.DataFrame] = None
):
    """
    💰 [예상 비용산정] 메인 관제 캔버스 (Cisco ACI Light-Canvas 테마 표준 100% 준수)
    1. 직급별 시간당 단가 관리 (DB 영구 저장, 동적 수정)
    2. 업무 시간 직접 수정 및 영구 보존 (아웃룩 '종일' 등 오버라이드)
    3. 조회 기준(기간, 팀, 팀원, 고객사) 연동 예상 청구 금액 산정
    4. 팀원별, 고객사별, 직급별 다차원 정산 대시보드
    """
    st.markdown("""
    <style>
    /* 🏛️ Cisco ACI 표준 테마: 예상 비용산정 전용 스타일 */

    /* 1. 상단 타이틀 및 설명 */
    .cost-main-title {
        font-size: 21px !important;
        font-weight: 800 !important;
        color: #002d42 !important;
        letter-spacing: -0.4px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .cost-main-desc {
        font-size: 13px !important;
        color: #475569 !important;
        margin-top: 4px;
        font-weight: 500;
        line-height: 1.5;
    }

    /* 2. 상단 필터 요약 박스 (텍스트 길이에 맞춘 플렉서블 핏) */
    .cost-filter-summary-card {
        background: #ffffff !important;
        border: 1.5px solid #cbd5e1 !important;
        border-radius: 8px !important;
        padding: 7px 14px !important;
        text-align: right !important;
        font-size: 12px !important;
        color: #334155 !important;
        box-shadow: 0 1px 4px rgba(0, 45, 66, 0.05) !important;
        width: fit-content !important;
        max-width: 100% !important;
        margin-left: auto !important;
        display: inline-block !important;
    }

    /* 3. 4대 KPI 메트릭 화이트 펄스 카드 (summary_view 표준 일원화) */
    .cost-kpi-row {
        display: flex;
        gap: 14px;
        margin-bottom: 20px;
        flex-wrap: wrap;
    }
    .cost-kpi-card-white {
        flex: 1;
        min-width: 180px;
        background: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
        padding: 16px 18px !important;
        box-shadow: 0 2px 8px rgba(0, 45, 66, 0.06) !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .cost-kpi-card-white:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 14px rgba(0, 45, 66, 0.12) !important;
    }
    .cost-kpi-card-white.top-navy { border-top: 5px solid #005073 !important; }
    .cost-kpi-card-white.top-blue { border-top: 5px solid #0284c7 !important; }
    .cost-kpi-card-white.top-green { border-top: 5px solid #10b981 !important; }
    .cost-kpi-card-white.top-purple { border-top: 5px solid #8b5cf6 !important; }

    .cost-kpi-label-gray {
        font-size: 12px !important;
        font-weight: 700 !important;
        color: #64748b !important;
        margin-bottom: 4px;
        letter-spacing: 0.2px;
    }
    .cost-kpi-val-bold {
        font-size: 26px !important;
        font-weight: 900 !important;
        letter-spacing: -0.5px;
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, monospace !important;
    }
    .cost-kpi-sub-text {
        margin-top: 6px;
        font-size: 11.5px !important;
        font-weight: 700;
    }

    /* 4. 가로 세그먼트 탭 라디오 버튼 (라디오 원형 완전 제거 & 캡슐 버튼화) */
    div.st-key-cost_sub_tab_radio [data-testid="stWidgetLabel"] {
        display: none !important;
    }
    div.st-key-cost_sub_tab_radio div[role="radiogroup"] {
        background: #ffffff !important;
        border: 1.5px solid #005f8a !important;
        border-radius: 8px !important;
        padding: 8px 12px !important;
        display: flex !important;
        flex-wrap: wrap !important;
        gap: 10px !important;
        box-shadow: 0 2px 6px rgba(0, 45, 66, 0.06) !important;
        margin-bottom: 16px !important;
    }
    div.st-key-cost_sub_tab_radio div[role="radiogroup"] label {
        background: #f1f5f9 !important;
        border: 1.2px solid #cbd5e1 !important;
        border-radius: 6px !important;
        padding: 7px 16px !important;
        margin: 0 !important;
        cursor: pointer !important;
        transition: all 0.15s ease-in-out !important;
    }
    div.st-key-cost_sub_tab_radio div[role="radiogroup"] label:hover {
        background: #e2e8f0 !important;
        border-color: #0284c7 !important;
    }
    div.st-key-cost_sub_tab_radio div[role="radiogroup"] label input[type="radio"] {
        display: none !important;
    }
    div.st-key-cost_sub_tab_radio div[role="radiogroup"] label div[data-testid="stMarkdownContainer"] p,
    div.st-key-cost_sub_tab_radio div[role="radiogroup"] label span {
        color: #002d42 !important;
        font-size: 13.5px !important;
        font-weight: 800 !important;
    }
    div.st-key-cost_sub_tab_radio div[role="radiogroup"] label[data-checked="true"],
    div.st-key-cost_sub_tab_radio div[role="radiogroup"] label:has(input:checked) {
        background: #005073 !important;
        border-color: #002d42 !important;
    }
    div.st-key-cost_sub_tab_radio div[role="radiogroup"] label[data-checked="true"] p,
    div.st-key-cost_sub_tab_radio div[role="radiogroup"] label:has(input:checked) p,
    div.st-key-cost_sub_tab_radio div[role="radiogroup"] label[data-checked="true"] span,
    div.st-key-cost_sub_tab_radio div[role="radiogroup"] label:has(input:checked) span {
        color: #ffffff !important;
        font-weight: 900 !important;
    }

    /* 5. 섹션 테이블/장표 헤더 배너 */
    .cost-table-header-cisco {
        background: #e0f2fe !important;
        border-left: 4px solid #0284c7 !important;
        padding: 9px 14px !important;
        border-radius: 6px !important;
        margin-bottom: 12px !important;
        font-size: 14.5px !important;
        font-weight: 800 !important;
        color: #002d42 !important;
        box-shadow: 0 1px 3px rgba(0, 45, 66, 0.04) !important;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    /* 6. 알림/안내 카드 */
    .cost-info-box-cisco {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 8px !important;
        padding: 10px 14px !important;
        font-size: 12.5px !important;
        color: #334155 !important;
        line-height: 1.6 !important;
        margin-bottom: 14px !important;
        box-shadow: 0 1px 3px rgba(0, 45, 66, 0.03) !important;
    }

    /* 7. 직급별 단가 설정 폼 내부 텍스트 완전 선명화 및 버튼 스타일 */
    div[data-testid="stForm"] {
        background: #ffffff !important;
        border: 1.5px solid #cbd5e1 !important;
        border-radius: 12px !important;
        padding: 24px 20px !important;
        box-shadow: 0 2px 8px rgba(0, 45, 66, 0.05) !important;
    }
    div[data-testid="stForm"] label,
    div[data-testid="stForm"] [data-testid="stWidgetLabel"] p,
    div[data-testid="stForm"] [data-testid="stWidgetLabel"] span {
        color: #000000 !important;
        font-weight: 900 !important;
        font-size: 14px !important;
    }
    div[data-testid="stForm"] button[kind="primary"] {
        background: linear-gradient(135deg, #005073 0%, #00364d 100%) !important;
        border: none !important;
        color: #ffffff !important;
        font-weight: 800 !important;
        font-size: 15px !important;
        padding: 10px 0 !important;
        border-radius: 8px !important;
        box-shadow: 0 2px 6px rgba(0, 45, 66, 0.2) !important;
    }
    div[data-testid="stForm"] input {
        background-color: #ffffff !important;
        color: #000000 !important;
        font-weight: 800 !important;
        font-size: 16px !important;
        border: 1.5px solid #cbd5e1 !important;
        border-radius: 6px !important;
    }
    div[data-testid="stForm"] button[kind="primary"]:hover {
        background: linear-gradient(135deg, #0284c7 0%, #005073 100%) !important;
    }

    /* 8. 직급별 단가 설정 number_input의 + - 버튼 바탕화면을 진한 회색조로 설정 */
    div[data-testid="stForm"] div[data-testid="stNumberInput"] button,
    div[data-testid="stForm"] button[data-testid="stNumberInputStepDown"],
    div[data-testid="stForm"] button[data-testid="stNumberInputStepUp"],
    div[data-testid="stNumberInput"] button {
        background-color: #475569 !important; /* 진한 회색조 (Slate-600) */
        color: #ffffff !important;
        border-color: #334155 !important;
        transition: background-color 0.15s ease !important;
    }
    div[data-testid="stForm"] div[data-testid="stNumberInput"] button:hover,
    div[data-testid="stForm"] button[data-testid="stNumberInputStepDown"]:hover,
    div[data-testid="stForm"] button[data-testid="stNumberInputStepUp"]:hover,
    div[data-testid="stNumberInput"] button:hover {
        background-color: #334155 !important; /* 호버 시 약간 더 짙은 회색조 */
        color: #ffffff !important;
    }
    div[data-testid="stForm"] div[data-testid="stNumberInput"] button svg,
    div[data-testid="stForm"] button[data-testid="stNumberInputStepDown"] svg,
    div[data-testid="stForm"] button[data-testid="stNumberInputStepUp"] svg,
    div[data-testid="stNumberInput"] button svg {
        fill: #ffffff !important;
        stroke: #ffffff !important;
        color: #ffffff !important;
    }
    div[data-testid="stForm"] div[data-testid="stNumberInput"] div[data-baseweb="input"] > div:last-child {
        background-color: #475569 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # 페이지별 타이틀 및 설명 동적 매핑
    page_titles = {
        "💰 팀원별 예상 청구금액": ("💰", "팀원별 프로젝트/지원 예상 청구금액", "기술본부 인력별 투입 공수 및 직급별 단가를 기준으로 사업본부 청구 금액을 산출합니다."),
        "💰 예상 비용산정": ("💰", "팀원별 프로젝트/지원 예상 청구금액", "기술본부 인력별 투입 공수 및 직급별 단가를 기준으로 사업본부 청구 금액을 산출합니다."),
        "💰 예상 비용산정 대시보드": ("💰", "팀원별 프로젝트/지원 예상 청구금액", "기술본부 인력별 투입 공수 및 직급별 단가를 기준으로 사업본부 청구 금액을 산출합니다."),
        "🏢 고객사별 청구 금액": ("💰", "팀원별 프로젝트/지원 예상 청구금액", "기술본부 인력별 투입 공수 및 직급별 단가를 기준으로 사업본부 청구 금액을 산출합니다."),
        "✏️ 업무 시간 직접 수정 장표": ("✏️", "업무 시간 직접 수정 장표", "아웃룩 '종일(9.0h)' 등록 작업 및 지원 공수를 직접 검토하고 영구 수정합니다."),
        "🕒 시간 수정 감사 이력": ("🕒", "시간 수정 감사 이력 타임라인", "인정 공수를 수정한 모든 내역의 변경 전/후, 사유, 수정자를 투명하게 보존 및 감사 추적합니다."),
        "⚙️ 직급별 시간당 단가 설정": ("⚙️", "직급별 시간당 단가 설정", "사업본부 청구용 직급별 시간당 단가(원/h)를 설정하고 DB에 영구 저장합니다.")
    }
    icon, title_txt, desc_txt = page_titles.get(curr_page, ("💰", "프로젝트/현장지원 예상 비용산정", "기술본부 인력의 투입 공수 및 직급별 단가를 기준으로 예상 청구 금액을 산출합니다."))

    # 2. 상단 헤더 및 조회 기준 요약 배지 바 (선명한 다크 네이비 & 화이트 배지)
    col_t1, col_t2 = st.columns([7, 3])
    with col_t1:
        st.markdown(f"""
        <div style="margin-bottom: 10px;">
            <div class="cost-main-title">
                <span>{icon}</span>
                <span>{title_txt}</span>
            </div>
            <div class="cost-main-desc">
                {desc_txt}
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_t2:
        cur_sel_period = st.session_state.get("cost_estimation_period_selector", "🗓️ 월간 전체 종합")
        if cur_sel_period != "🗓️ 월간 전체 종합":
            period_text = f"{month_desc} ({cur_sel_period.replace('📌 ', '').strip()})" if month_desc else cur_sel_period.replace('📌 ', '').strip()
        else:
            period_text = month_desc if month_desc else "전체 기간"
        team_text = selected_team if selected_team else "전체 팀"
        worker_text = worker_desc if worker_desc else "전체 인원"
        st.markdown(f"""
        <div style="display: flex; justify-content: flex-end; width: 100%;">
            <div class="cost-filter-summary-card">
                <div>📅 <b>기간:</b> <span style="color: #005073; font-weight: 800;">{period_text}</span></div>
                <div style="margin-top: 3px;">🏢 <b>대상:</b> <span style="color: #0284c7; font-weight: 800;">{team_text}</span> | <span style="color: #6366f1; font-weight: 700;">{worker_text}</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ⚖️ 근로기준법 제56조 준수 안내 바 (상시 1.5배 가산 자동 적용 명시 & 국가법령정보센터 조문 링크)
    st.markdown("""
    <div style="background: #f0fdf4; border: 1.2px solid #86efac; border-left: 5px solid #16a34a; border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
        <div>
            <div style="font-size: 13px; font-weight: 700; color: #14532d; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                <span>⚖️ <b>근로기준법 제56조 준수:</b> 야간 근로(22:00~06:00) 및 주말·휴일 지원 공수에 대해 <b>1.5배 할증 가산(50% 가산)</b>이 상시 자동 적용되어 청구 금액에 반영됩니다.</span>
            </div>
            <div style="margin-top: 5px; font-size: 12px; font-weight: 600; color: #166534; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                <span>📖 관련 법령:</span>
                <a href="https://www.law.go.kr/LSW//lsLinkCommonInfo.do?lsJoLnkSeq=1025590551&chrClsCd=010202&ancYnChk=" target="_blank" rel="noopener noreferrer" style="color: #0284c7; font-weight: 800; text-decoration: underline;">[국가법령정보센터 | 조문정보]</a>
                <span style="color: #64748b; font-size: 11.5px;">(클릭 시 근로기준법 제56조 조문 새 창 열기 ↗)</span>
            </div>
        </div>
        <div>
            <div style="font-size: 12px; font-weight: 800; color: #15803d; background: #dcfce7; padding: 4px 12px; border-radius: 4px; border: 1px solid #bbf7d0; white-space: nowrap;">
                상시 자동 적용 (배율: 1.5배)
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 🎓 비용 산정 정책 안내 (교육, 휴가 및 비청구 사내업무 청구 제외)
    st.markdown("""
    <div style="background: #f8fafc; border: 1.2px solid #cbd5e1; border-left: 5px solid #0284c7; border-radius: 8px; padding: 9px 14px; margin-bottom: 16px; font-size: 12.5px; color: #334155; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
        <div>
            <span>💡 <b>비용 산정 정책:</b> 구분이 <b>[교육]</b>·<b>[휴가]</b>인 항목 및 비청구 사내업무(<b>1on1, 내부업무</b> 등)는 외부 고객사 청구 대상이 아니므로 <b>예상 청구 금액 산정 대상에서 원천 제외</b>됩니다. (고객사 정산표에서 제외 목록을 실시간 추가/저장 가능)</span>
        </div>
        <span style="background: #e0f2fe; color: #0284c7; border: 1px solid #bae6fd; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700;">교육·휴가·사내업무 제외</span>
    </div>
    """, unsafe_allow_html=True)

    # =========================================================
    # 📅 보고서 조회 주기 선택 (월간 전체 종합 vs 각 주차별 상세 드릴다운)
    # =========================================================
    df_scope = df.copy()
    available_weeks = get_available_weeks_for_df(df_scope, month_desc=month_desc)
    if not available_weeks and df_filtered_base is not None and not df_filtered_base.empty:
        available_weeks = get_available_weeks_for_df(df_filtered_base, month_desc=month_desc)
    if not available_weeks and df_raw is not None and not df_raw.empty:
        available_weeks = get_available_weeks_for_df(df_raw, month_desc=month_desc)

    period_options = ["🗓️ 월간 전체 종합"] + [f"📌 {w}" for w in available_weeks]

    st.markdown("""
    <style>
        div.st-key-cost_estimation_period_selector [data-testid="stWidgetLabel"],
        div.st-key-cost_estimation_period_selector [data-testid="stWidgetLabel"] *,
        div.st-key-cost_estimation_period_selector label,
        div.st-key-cost_estimation_period_selector label * {
            color: #002d42 !important;
            font-size: 14.5px !important;
            font-weight: 800 !important;
        }
        div.st-key-cost_estimation_period_selector div[role="radiogroup"] {
            background: #ffffff !important;
            border: 1.5px solid #005f8a !important;
            border-radius: 8px !important;
            padding: 8px 14px !important;
            display: flex !important;
            flex-wrap: wrap !important;
            gap: 10px !important;
            box-shadow: 0 2px 6px rgba(0,45,66,0.06) !important;
            margin-bottom: 16px !important;
        }
        div.st-key-cost_estimation_period_selector div[role="radiogroup"] label {
            background: #f1f5f9 !important;
            border: 1.2px solid #cbd5e1 !important;
            border-radius: 6px !important;
            padding: 5px 12px !important;
            margin: 0 !important;
            cursor: pointer !important;
            transition: all 0.15s ease-in-out !important;
        }
        div.st-key-cost_estimation_period_selector div[role="radiogroup"] label:hover {
            background: #e2e8f0 !important;
            border-color: #0284c7 !important;
        }
        div.st-key-cost_estimation_period_selector div[role="radiogroup"] label p,
        div.st-key-cost_estimation_period_selector div[role="radiogroup"] label span {
            color: #002d42 !important;
            font-size: 13px !important;
            font-weight: 800 !important;
        }
        div.st-key-cost_estimation_period_selector div[role="radiogroup"] label[data-checked="true"],
        div.st-key-cost_estimation_period_selector div[role="radiogroup"] label:has(input:checked) {
            background: #005073 !important;
            border-color: #002d42 !important;
        }
        div.st-key-cost_estimation_period_selector div[role="radiogroup"] label[data-checked="true"] p,
        div.st-key-cost_estimation_period_selector div[role="radiogroup"] label:has(input:checked) p,
        div.st-key-cost_estimation_period_selector div[role="radiogroup"] label[data-checked="true"] span,
        div.st-key-cost_estimation_period_selector div[role="radiogroup"] label:has(input:checked) span {
            color: #ffffff !important;
            font-weight: 900 !important;
        }
    </style>
    <div style="font-size: 14.5px; font-weight: 800; color: #002d42 !important; margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
        <span>🗓️</span>
        <span style="color: #002d42 !important; font-weight: 800 !important;">보고서 조회 주기 선택 (월간 / 주간 드릴다운)</span>
    </div>
    """, unsafe_allow_html=True)

    if available_weeks:
        sel_period = st.radio(
            "보고서 조회 주기 선택 (월간 / 주간 드릴다운)",
            options=period_options,
            horizontal=True,
            key="cost_estimation_period_selector",
            label_visibility="collapsed"
        )
    else:
        sel_period = "🗓️ 월간 전체 종합"

    # 선택된 주기에 따른 활성 데이터셋(df_active) 분기
    if sel_period != "🗓️ 월간 전체 종합":
        target_week = sel_period.replace("📌 ", "").strip()
        # 💡 월 경계(예: 8/31~9/6)에 걸친 주차도 7일 전체 데이터가 누락 없이 온전히 조회되도록 df_filtered_base 또는 df_raw에서 주간 데이터 추출
        if df_filtered_base is not None and not df_filtered_base.empty and "week_label" in df_filtered_base.columns:
            df_active = df_filtered_base[df_filtered_base["week_label"] == target_week].copy()
        elif df_raw is not None and not df_raw.empty and "week_label" in df_raw.columns:
            df_active = df_raw[df_raw["week_label"] == target_week].copy()
            if selected_team not in ["전체", "전체 팀"] and not df_active.empty:
                df_active["worker_team"] = df_active["worker_name"].map(team_mappings).fillna(df_active.get("worker_team", "")).fillna(UNASSIGNED_TEAM)
                df_active = df_active[df_active["worker_team"].apply(lambda t: is_same_team(t, selected_team))]
        else:
            df_active = df_scope[df_scope["week_label"] == target_week].copy()
    else:
        df_active = df_scope.copy()

    # -------------------------------------------------------------
    # 📅 보고서 조회 기준 기간 산출 (월간: 'YYYY년 M월', 주간 드릴다운: '며칠~며칠' 반영)
    # -------------------------------------------------------------
    if sel_period != "🗓️ 월간 전체 종합":
        # 주간 드릴다운인 경우: 주차명 및 며칠~며칠 유지 (예: "9월 1주차 (08.31~09.06)")
        target_week = sel_period.replace("📌 ", "").strip()
        current_report_period = target_week
        period_header_suffix = f" ({target_week})"
    else:
        # 월간 전체 종합인 경우: 'YYYY년 M월' 형태로 깔끔하게 표기
        raw_m = str(month_desc).strip() if month_desc else ""
        match_ym = re.match(r"^(\d{4})-(\d{1,2})$", raw_m)
        if match_ym:
            current_report_period = f"{match_ym.group(1)}년 {int(match_ym.group(2))}월"
        elif "," in raw_m and any(re.search(r"\d{4}-\d{1,2}", p) for p in raw_m.split(",")):
            formatted_list = []
            for p in raw_m.split(","):
                m_sub = re.search(r"(\d{4})-(\d{1,2})", p)
                if m_sub:
                    formatted_list.append(f"{m_sub.group(1)}년 {int(m_sub.group(2))}월")
                else:
                    formatted_list.append(p.strip())
            current_report_period = ", ".join(formatted_list)
        elif "년" in raw_m and "월" in raw_m and "~" not in raw_m:
            current_report_period = raw_m
        elif raw_m and raw_m != "전체 기간":
            current_report_period = raw_m
        else:
            # month_desc가 "전체 기간"이거나 비어있을 때 데이터에서 실제 월 또는 일자 범위 확인
            if "start_time" in df_active.columns and not df_active["start_time"].dropna().empty:
                valid_st = pd.to_datetime(df_active["start_time"], errors="coerce").dropna()
                if not valid_st.empty:
                    min_dt = valid_st.min()
                    max_dt = valid_st.max()
                    if min_dt.year == max_dt.year and min_dt.month == max_dt.month:
                        current_report_period = f"{min_dt.year}년 {min_dt.month}월"
                    else:
                        current_report_period = f"{min_dt.strftime('%Y.%m.%d')} ~ {max_dt.strftime('%Y.%m.%d')}"
                else:
                    current_report_period = "전체 기간"
            else:
                current_report_period = "전체 기간"

        period_header_suffix = f" ({current_report_period})" if current_report_period != "전체 기간" else ""

    # 🚫 비청구 대상(1on1, 내부업무 등) 관리자 제외 목록 로드 및 세션 동기화
    if "cost_excluded_clients" not in st.session_state:
        st.session_state["cost_excluded_clients"] = CostEstimationService.get_excluded_clients()
    current_excluded_clients = list(st.session_state.get(
        "multiselect_excluded_cost_clients",
        st.session_state.get("cost_excluded_clients", [])
    ))

    # 1. 계산된 예상 비용 데이터프레임 도출 (선택된 주기 df_active 기준, 비청구 제외 목록 적용)
    df_calc = CostEstimationService.calculate_costs(df_active, excluded_clients=current_excluded_clients)
    kpis = CostEstimationService.get_cost_summary_kpis(df_calc)

    # 3. 상단 4대 메트릭 화이트 펄스 카드
    tot_cost_str = f"₩ {kpis['total_cost']:,}"
    tot_hours_str = f"{kpis['total_billable_hours']:,.1f} h"
    adj_pct = (kpis['adjusted_count'] / max(1, kpis['total_tasks'])) * 100
    regular_hours = max(0.0, kpis['total_billable_hours'] - kpis['total_overtime_hours'])

    st.markdown(f"""
    <div class="cost-kpi-row">
        <div class="cost-kpi-card-white top-navy">
            <div class="cost-kpi-label-gray">💳 총 예상 청구금액 (1.5배 할증반영)</div>
            <div class="cost-kpi-val-bold" style="color: #005073;">{tot_cost_str}</div>
            <div class="cost-kpi-sub-text" style="color: #0284c7;">기본 ₩{kpis['total_base_cost']:,} + 할증가산 ₩{kpis['total_overtime_premium']:,}</div>
        </div>
        <div class="cost-kpi-card-white top-blue">
            <div class="cost-kpi-label-gray">⏱️ 총 투입 인정 공수</div>
            <div class="cost-kpi-val-bold" style="color: #0284c7;">{tot_hours_str}</div>
            <div class="cost-kpi-sub-text" style="color: #10b981;">일반 {regular_hours:,.1f}h | 야간·주말 {kpis['total_overtime_hours']:,.1f}h (1.5배)</div>
        </div>
        <div class="cost-kpi-card-white top-green">
            <div class="cost-kpi-label-gray">👥 투입 인력 / 평균 단가</div>
            <div class="cost-kpi-val-bold" style="color: #10b981;">{kpis['worker_count']}명</div>
            <div class="cost-kpi-sub-text" style="color: #64748b;">가중평균 {kpis['avg_hourly_rate']:,}원/h (총 {kpis['total_tasks']:,}건)</div>
        </div>
        <div class="cost-kpi-card-white top-purple">
            <div class="cost-kpi-label-gray">✏️ 시간 보정(수정) 작업</div>
            <div class="cost-kpi-val-bold" style="color: #8b5cf6;">{kpis['adjusted_count']}건</div>
            <div class="cost-kpi-sub-text" style="color: #8b5cf6;">관리자 인정 공수 영구 오버라이드 ({adj_pct:.1f}%)</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # =========================================================
    # 1. 👤 팀원별 예상 청구금액
    # =========================================================
    if curr_page in ["💰 팀원별 예상 청구금액", "💰 예상 비용산정", "💰 예상 비용산정 대시보드", "🏢 고객사별 청구 금액"]:
        st.markdown(f'<div class="cost-table-header-cisco"><span>👤</span><span>팀원별 투입 공수 및 예상 청구 금액 정산표{period_header_suffix}</span></div>', unsafe_allow_html=True)

        worker_df = CostEstimationService.get_worker_cost_summary(df_calc)
        if worker_df.empty:
            st.info("조회 기준에 해당하는 팀원 작업 데이터가 없습니다.")
        else:
            col_w1, col_w2 = st.columns([6, 4])
            with col_w1:
                display_worker_df = worker_df.copy()
                display_worker_df = display_worker_df[[
                    "worker_name", "worker_team", "worker_title", "hourly_rate",
                    "total_hours", "overtime_hours", "base_cost", "overtime_premium", "total_cost",
                    "task_count", "adjusted_count"
                ]]
                display_worker_df.columns = [
                    "팀원명", "소속팀", "직급", "시간당 단가(원)",
                    "총 인정공수(h)", "야간·주말(h)", "기본 금액(원)", "할증 가산액(원)", "최종 청구금액(원)",
                    "작업 건수", "보정 건수"
                ]

                st.dataframe(
                    display_worker_df.style.format({
                        "시간당 단가(원)": "{:,.0f}원",
                        "총 인정공수(h)": "{:,.1f}h",
                        "야간·주말(h)": "{:,.1f}h",
                        "기본 금액(원)": "₩ {:,.0f}",
                        "할증 가산액(원)": "+₩ {:,.0f}",
                        "최종 청구금액(원)": "₩ {:,.0f}",
                        "작업 건수": "{:,}건",
                        "보정 건수": "{:,}건"
                    }),
                    use_container_width=True,
                    height=360,
                    hide_index=True
                )

                try:
                    safe_slug = re.sub(r'[\\/*?:"<>| ~()]', '_', current_report_period).strip('_')
                    safe_slug = re.sub(r'_+', '_', safe_slug)[:25]
                    file_name_suffix = f"_{safe_slug}" if safe_slug else ""
                    excel_worker_data = ExcelExportService.generate_cost_estimation_report(
                        df_calc=df_calc,
                        worker_df=worker_df,
                        title_suffix=current_report_period
                    )
                    st.download_button(
                        label="📥 팀원별 정산 엑셀 다운로드 (첫 탭: 요약표 / 나머지: 개인장표)",
                        data=excel_worker_data,
                        file_name=f"팀원별_예상청구비용{file_name_suffix}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="btn_dl_worker_cost_excel",
                        type="primary",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"엑셀 생성 오류: {e}")

            with col_w2:
                top_workers = worker_df.head(10).sort_values(by="total_cost", ascending=True)
                fig_w = px.bar(
                    top_workers,
                    x="total_cost",
                    y="worker_name",
                    orientation="h",
                    text="total_cost",
                    title="🏆 예상 청구 금액 Top 10 팀원",
                    labels={"total_cost": "예상 청구금액 (원)", "worker_name": "팀원"}
                )
                fig_w.update_traces(
                    marker_color="#005073",
                    texttemplate='₩ %{text:,.0f}',
                    textposition='outside',
                    textfont=dict(color="#000000", size=12, family="Pretendard, sans-serif")
                )
                fig_w.update_layout(
                    template="plotly_white",
                    paper_bgcolor="#ffffff",
                    plot_bgcolor="#ffffff",
                    font=dict(color="#000000", family="Pretendard, sans-serif"),
                    title=dict(font=dict(size=14, color="#000000", family="Pretendard, sans-serif")),
                    xaxis=dict(
                        title=dict(text="예상 청구금액 (원)", font=dict(color="#000000", size=12, family="Pretendard, sans-serif")),
                        tickfont=dict(color="#000000", size=11, family="Pretendard, sans-serif"),
                        showgrid=True,
                        gridcolor="#e2e8f0"
                    ),
                    yaxis=dict(
                        title=dict(text="팀원", font=dict(color="#000000", size=12, family="Pretendard, sans-serif")),
                        tickfont=dict(color="#000000", size=12, family="Pretendard, sans-serif"),
                        showgrid=False
                    ),
                    height=360,
                    margin=dict(l=20, r=100, t=40, b=30),
                    showlegend=False
                )
                st.plotly_chart(fig_w, use_container_width=True)

        st.markdown(f'<div class="cost-table-header-cisco" style="margin-top: 20px;"><span>👔</span><span>직급별 공수 및 청구 금액 점유율{period_header_suffix}</span></div>', unsafe_allow_html=True)
        title_df = CostEstimationService.get_title_cost_summary(df_calc)
        if not title_df.empty:
            col_t_tab1, col_t_tab2 = st.columns([6, 4])
            with col_t_tab1:
                disp_title_df = title_df.copy()
                disp_title_df = disp_title_df[[
                    "worker_title", "hourly_rate", "worker_count", "total_hours", "overtime_hours",
                    "base_cost", "overtime_premium", "total_cost", "cost_share_pct"
                ]]
                disp_title_df.columns = [
                    "직급", "단가(원/h)", "투입인원", "총 인정공수(h)", "야간·주말(h)",
                    "기본 금액(원)", "할증 가산액(원)", "최종 청구금액(원)", "금액 점유율(%)"
                ]
                st.dataframe(
                    disp_title_df.style.format({
                        "단가(원/h)": "{:,.0f}원",
                        "투입인원": "{:,}명",
                        "총 인정공수(h)": "{:,.1f}h",
                        "야간·주말(h)": "{:,.1f}h",
                        "기본 금액(원)": "₩ {:,.0f}",
                        "할증 가산액(원)": "+₩ {:,.0f}",
                        "최종 청구금액(원)": "₩ {:,.0f}",
                        "금액 점유율(%)": "{:.1f}%"
                    }),
                    use_container_width=True,
                    height=240,
                    hide_index=True
                )
            with col_t_tab2:
                fig_t = px.pie(
                    title_df,
                    names="worker_title",
                    values="total_cost",
                    title="직급별 청구 금액 비중",
                    hole=0.45,
                    color_discrete_sequence=["#005073", "#0284c7", "#06b6d4", "#10b981", "#64748b"]
                )
                fig_t.update_traces(
                    textposition='inside',
                    textinfo='percent+label',
                    textfont=dict(size=12, color="#ffffff", family="Pretendard, sans-serif")
                )
                fig_t.update_layout(
                    template="plotly_white",
                    paper_bgcolor="#ffffff",
                    plot_bgcolor="#ffffff",
                    font=dict(color="#000000", family="Pretendard, sans-serif"),
                    title=dict(font=dict(size=14, color="#000000", family="Pretendard, sans-serif")),
                    legend=dict(font=dict(color="#000000", size=11, family="Pretendard, sans-serif")),
                    height=240,
                    margin=dict(l=10, r=10, t=35, b=10)
                )
                st.plotly_chart(fig_t, use_container_width=True)

        # -------------------------------------------------------------
        # 🏢 고객사/프로젝트별 예상 청구 금액 정산표 (직급별 점유율 바로 아래 배치)
        # -------------------------------------------------------------
        st.markdown(f'<div class="cost-table-header-cisco" style="margin-top: 24px;"><span>🏢</span><span>고객사/프로젝트별 예상 청구 금액 정산표{period_header_suffix}</span></div>', unsafe_allow_html=True)

        # 🚫 청구 제외 대상(1on1, 사내업무 등) 관리 패널 & 현재 제외 배지
        raw_clients_pool = []
        if "client_name" in df_active.columns:
            raw_clients_pool.extend([str(c).strip() for c in df_active["client_name"].dropna().unique() if str(c).strip()])
        if df_raw is not None and not df_raw.empty and "client_name" in df_raw.columns:
            raw_clients_pool.extend([str(c).strip() for c in df_raw["client_name"].dropna().unique() if str(c).strip()])
        raw_clients_pool.extend(current_excluded_clients)
        all_candidate_clients = sorted(list(set(raw_clients_pool)))

        if "multiselect_excluded_cost_clients" not in st.session_state:
            st.session_state["multiselect_excluded_cost_clients"] = [c for c in current_excluded_clients if c in all_candidate_clients]

        # 현재 제외 중인 항목 배지 표시
        if current_excluded_clients:
            badge_spans = " ".join([
                f'<span style="display: inline-block; background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; padding: 2px 8px; border-radius: 4px; font-weight: 700; margin: 2px; font-size: 11.5px;">🚫 {c}</span>'
                for c in current_excluded_clients
            ])
            st.markdown(f"""
            <div style="background: #ffffff; border: 1.2px solid #fecaca; border-left: 4px solid #ef4444; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 12.5px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                    <div>
                        <span style="font-weight: 800; color: #991b1b;">🚫 현재 청구 제외 대상 ({len(current_excluded_clients)}건):</span> {badge_spans}
                    </div>
                    <span style="color: #64748b; font-size: 11px;">※ 위 항목은 청구 금액 정산표, 파이 차트, 총 청구 KPI 및 엑셀 다운로드에서 완전 제외됩니다.</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        with st.expander("⚙️ 청구 제외 고객사/사내업무 설정 (1on1, 사내미팅 등 비청구 대상 추가/삭제)", expanded=False):
            st.markdown("""
            <div style="font-size: 12.5px; color: #475569; margin-bottom: 10px; line-height: 1.5;">
                💡 <b>1on1(팀장 1:1 미팅)</b>, <b>내부업무</b> 등 외부 고객사에 청구되지 않아야 하는 비청구 사내 항목을 선택하세요.<br>
                목록을 수정한 후 <b>[💾 제외 목록 영구 저장]</b> 버튼을 누르면 DB 및 시스템 설정에 영구 보존됩니다.
            </div>
            """, unsafe_allow_html=True)

            col_ex1, col_ex2, col_ex3 = st.columns([7, 2, 1.5])
            with col_ex1:
                selected_excluded = st.multiselect(
                    "청구 금액 정산에서 제외할 고객사/사내업무 선택:",
                    options=all_candidate_clients,
                    key="multiselect_excluded_cost_clients",
                    placeholder="제외할 고객사 또는 업무명을 검색/선택하세요...",
                    label_visibility="collapsed"
                )
            with col_ex2:
                if st.button("💾 제외 목록 영구 저장", key="btn_save_excluded_clients", type="primary", use_container_width=True):
                    CostEstimationService.save_excluded_clients(selected_excluded)
                    st.session_state["cost_excluded_clients"] = selected_excluded
                    st.session_state["multiselect_excluded_cost_clients"] = selected_excluded
                    st.toast("✅ 청구 제외 목록이 영구 저장되었습니다!", icon="💾")
                    st.rerun()
            with col_ex3:
                if st.button("🔄 기본값 복원", key="btn_reset_excluded_clients", use_container_width=True, help="기본 제외 목록 ['1on1', '내부업무']로 복원합니다."):
                    CostEstimationService.save_excluded_clients(CostEstimationService.DEFAULT_EXCLUDED_CLIENTS)
                    st.session_state["cost_excluded_clients"] = list(CostEstimationService.DEFAULT_EXCLUDED_CLIENTS)
                    st.session_state["multiselect_excluded_cost_clients"] = list(CostEstimationService.DEFAULT_EXCLUDED_CLIENTS)
                    st.toast("🔄 기본 제외 목록(['1on1', '내부업무'])으로 복원되었습니다.", icon="🔄")
                    st.rerun()
        client_df = CostEstimationService.get_client_cost_summary(df_calc)
        if client_df.empty:
            st.info("조회 기준에 해당하는 고객사 작업 데이터가 없습니다.")
        else:
            col_c1, col_c2 = st.columns([6, 4])
            with col_c1:
                disp_client_df = client_df.copy()
                disp_client_df = disp_client_df[[
                    "client_name", "worker_count", "total_hours", "overtime_hours",
                    "base_cost", "overtime_premium", "total_cost", "task_count", "adjusted_count"
                ]]
                disp_client_df.columns = [
                    "고객사명", "투입 인원수", "총 인정 공수(h)", "야간·주말(h)",
                    "기본 금액(원)", "할증 가산액(원)", "최종 청구금액(원)", "작업 건수", "보정 건수"
                ]
                st.dataframe(
                    disp_client_df.style.format({
                        "투입 인원수": "{:,}명",
                        "총 인정 공수(h)": "{:,.1f}h",
                        "야간·주말(h)": "{:,.1f}h",
                        "기본 금액(원)": "₩ {:,.0f}",
                        "할증 가산액(원)": "+₩ {:,.0f}",
                        "최종 청구금액(원)": "₩ {:,.0f}",
                        "작업 건수": "{:,}건",
                        "보정 건수": "{:,}건"
                    }),
                    use_container_width=True,
                    height=380,
                    hide_index=True
                )

                csv_c_data = disp_client_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 고객사별 정산표 CSV 다운로드",
                    data=csv_c_data,
                    file_name=f"고객사별_예상청구비용_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key="btn_dl_client_cost_csv"
                )

            with col_c2:
                top_clients = client_df.head(8)
                fig_c = px.pie(
                    top_clients,
                    names="client_name",
                    values="total_cost",
                    title="🏆 주요 고객사 청구 금액 점유율",
                    hole=0.45,
                    color_discrete_sequence=["#005073", "#0284c7", "#0ea5e9", "#14b8a6", "#10b981", "#f59e0b", "#8b5cf6", "#64748b"]
                )
                fig_c.update_traces(
                    textposition='inside',
                    textinfo='percent+label',
                    textfont=dict(size=11, color="#ffffff", family="Pretendard, sans-serif")
                )
                fig_c.update_layout(
                    template="plotly_white",
                    paper_bgcolor="#ffffff",
                    plot_bgcolor="#ffffff",
                    font=dict(color="#000000", family="Pretendard, sans-serif"),
                    title=dict(font=dict(size=14, color="#000000", family="Pretendard, sans-serif")),
                    legend=dict(font=dict(color="#000000", size=11, family="Pretendard, sans-serif")),
                    height=380,
                    margin=dict(l=10, r=10, t=40, b=20)
                )
                st.plotly_chart(fig_c, use_container_width=True)

        # -------------------------------------------------------------
        # 📈 전월 대비 MoM 월별 청구 추이 및 증감 분석 (기능 5)
        # -------------------------------------------------------------
        scope_title = f"[{selected_team}]" if selected_team and selected_team != "전체 팀" else "[전체 기술본부]"
        st.markdown(f'<div class="cost-table-header-cisco" style="margin-top: 24px;"><span>📈</span><span>{scope_title} 월별 청구 추이 및 전월 대비(MoM) 증감 분석</span></div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="cost-info-box-cisco">
            💡 <b>월별 청구 추이 가이드:</b> <b>{scope_title}</b> 인력의 최근 12개월간 월별 청구 금액 및 투입 공수 변화 추이를 확인하고, 전월 대비(MoM) 증감률(%)을 통해 지원 규모의 변동성을 파악합니다.
        </div>
        """, unsafe_allow_html=True)

        # 🎯 현재 선택된 팀/팀원/고객사 필터가 반영된 베이스 데이터셋 적용 (월 필터만 제외하여 전체 기간 월별 추이 산출)
        if df_filtered_base is not None and not df_filtered_base.empty:
            trend_target_df = df_filtered_base
        else:
            trend_target_df = df_raw.copy()
            if selected_team and selected_team != "전체 팀":
                team_workers = [w for w, t in team_mappings.items() if t == selected_team]
                if team_workers:
                    trend_target_df = trend_target_df[trend_target_df["worker_name"].isin(team_workers)]
                elif "worker_team" in trend_target_df.columns:
                    trend_target_df = trend_target_df[trend_target_df["worker_team"] == selected_team]

        trend_df = CostEstimationService.get_monthly_billing_trend(trend_target_df)
        if trend_df.empty:
            st.info("월별 청구 추이를 분석할 완료 작업 데이터가 충분하지 않습니다.")
        else:
            latest_row = trend_df.iloc[-1]
            prev_row = trend_df.iloc[-2] if len(trend_df) >= 2 else None

            latest_cost_str = f"₩ {int(latest_row['total_cost']):,}"
            cost_mom_pct = latest_row.get("mom_cost_pct", 0.0)
            cost_mom_diff = int(latest_row.get("mom_diff_cost", 0))

            if pd.isna(cost_mom_pct) or prev_row is None:
                cost_mom_desc = "전월 데이터 없음"
                cost_mom_color = "#64748b"
            elif cost_mom_diff >= 0:
                cost_mom_desc = f"▲ +{cost_mom_pct:.1f}% (+₩{cost_mom_diff:,})"
                cost_mom_color = "#10b981"
            else:
                cost_mom_desc = f"▼ {cost_mom_pct:.1f}% (-₩{abs(cost_mom_diff):,})"
                cost_mom_color = "#ef4444"

            latest_hours_str = f"{latest_row['total_hours']:,.1f} h"
            hours_mom_pct = latest_row.get("mom_hours_pct", 0.0)
            hours_mom_diff = float(latest_row.get("mom_diff_hours", 0.0))

            if pd.isna(hours_mom_pct) or prev_row is None:
                hours_mom_desc = "전월 데이터 없음"
                hours_mom_color = "#64748b"
            elif hours_mom_diff >= 0:
                hours_mom_desc = f"▲ +{hours_mom_pct:.1f}% (+{hours_mom_diff:.1f}h)"
                hours_mom_color = "#10b981"
            else:
                hours_mom_desc = f"▼ {hours_mom_pct:.1f}% ({hours_mom_diff:.1f}h)"
                hours_mom_color = "#ef4444"

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                st.markdown(f"""
                <div style="background: #ffffff; border: 1.5px solid #cbd5e1; border-top: 4px solid #005073; border-radius: 8px; padding: 12px 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.04);">
                    <div style="font-size: 11.5px; font-weight: 700; color: #64748b;">📅 {latest_row['year_month']} 청구 금액</div>
                    <div style="font-size: 20px; font-weight: 900; color: #005073; margin-top: 2px;">{latest_cost_str}</div>
                    <div style="font-size: 11px; font-weight: 800; color: {cost_mom_color}; margin-top: 4px;">MoM {cost_mom_desc}</div>
                </div>
                """, unsafe_allow_html=True)
            with col_m2:
                st.markdown(f"""
                <div style="background: #ffffff; border: 1.5px solid #cbd5e1; border-top: 4px solid #0284c7; border-radius: 8px; padding: 12px 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.04);">
                    <div style="font-size: 11.5px; font-weight: 700; color: #64748b;">⏱️ {latest_row['year_month']} 투입 인정 공수</div>
                    <div style="font-size: 20px; font-weight: 900; color: #0284c7; margin-top: 2px;">{latest_hours_str}</div>
                    <div style="font-size: 11px; font-weight: 800; color: {hours_mom_color}; margin-top: 4px;">MoM {hours_mom_desc}</div>
                </div>
                """, unsafe_allow_html=True)
            with col_m3:
                st.markdown(f"""
                <div style="background: #ffffff; border: 1.5px solid #cbd5e1; border-top: 4px solid #10b981; border-radius: 8px; padding: 12px 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.04);">
                    <div style="font-size: 11.5px; font-weight: 700; color: #64748b;">⚖️ 기본 vs 할증 가산액</div>
                    <div style="font-size: 17px; font-weight: 900; color: #10b981; margin-top: 4px;">+₩ {int(latest_row['overtime_premium']):,}</div>
                    <div style="font-size: 11px; font-weight: 700; color: #64748b; margin-top: 4px;">기본: ₩{int(latest_row['base_cost']):,} (야간/주말 {latest_row['overtime_hours']:.1f}h)</div>
                </div>
                """, unsafe_allow_html=True)
            with col_m4:
                st.markdown(f"""
                <div style="background: #ffffff; border: 1.5px solid #cbd5e1; border-top: 4px solid #8b5cf6; border-radius: 8px; padding: 12px 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.04);">
                    <div style="font-size: 11.5px; font-weight: 700; color: #64748b;">👥 {latest_row['year_month']} 투입 인원 / 건수</div>
                    <div style="font-size: 20px; font-weight: 900; color: #8b5cf6; margin-top: 2px;">{int(latest_row['worker_count'])}명</div>
                    <div style="font-size: 11px; font-weight: 700; color: #64748b; margin-top: 4px;">총 {int(latest_row['task_count']):,}건 완료 작업</div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

            # 복합 차트: 월별 청구액 막대 + 투입 공수 꺾은선
            fig_mom = go.Figure()
            fig_mom.add_trace(go.Bar(
                x=trend_df["year_month"],
                y=trend_df["base_cost"],
                name="기본 청구액 (원)",
                marker_color="#005073",
                hovertemplate="%{x}<br>기본 금액: ₩%{y:,.0f}<extra></extra>"
            ))
            fig_mom.add_trace(go.Bar(
                x=trend_df["year_month"],
                y=trend_df["overtime_premium"],
                name="야간/주말 할증 가산액 (원)",
                marker_color="#10b981",
                hovertemplate="%{x}<br>할증 가산: ₩%{y:,.0f}<extra></extra>"
            ))
            fig_mom.add_trace(go.Scatter(
                x=trend_df["year_month"],
                y=trend_df["total_hours"],
                name="투입 공수 (h)",
                mode="lines+markers+text",
                text=trend_df["total_hours"].apply(lambda v: f"{v:.1f}h"),
                textposition="top center",
                textfont=dict(color="#0284c7", size=11, family="Pretendard, sans-serif"),
                line=dict(color="#0284c7", width=3),
                marker=dict(size=7, color="#0284c7"),
                yaxis="y2",
                hovertemplate="%{x}<br>투입 공수: %{y:.1f}h<extra></extra>"
            ))

            fig_mom.update_layout(
                barmode="stack",
                template="plotly_white",
                paper_bgcolor="#ffffff",
                plot_bgcolor="#ffffff",
                font=dict(color="#000000", family="Pretendard, sans-serif"),
                title=dict(text="📊 월별 청구 금액(막대) & 투입 공수(꺾은선) 추이", font=dict(size=14, color="#000000", family="Pretendard, sans-serif")),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11, color="#000000")),
                xaxis=dict(title=dict(text="월 (YYYY-MM)", font=dict(color="#000000", size=12)), tickfont=dict(color="#000000", size=11), showgrid=False),
                yaxis=dict(title=dict(text="청구 금액 (원)", font=dict(color="#000000", size=12)), tickfont=dict(color="#000000", size=11), showgrid=True, gridcolor="#e2e8f0"),
                yaxis2=dict(title=dict(text="투입 공수 (h)", font=dict(color="#0284c7", size=12)), tickfont=dict(color="#0284c7", size=11), overlaying="y", side="right", showgrid=False),
                height=340,
                margin=dict(l=20, r=40, t=50, b=30)
            )
            st.plotly_chart(fig_mom, use_container_width=True)

            # 월별 정산 내역 및 MoM 지표 테이블
            disp_mom_df = trend_df.copy()
            disp_mom_df = disp_mom_df.sort_values(by="year_month", ascending=False).reset_index(drop=True)
            disp_mom_df["mom_cost_str"] = disp_mom_df.apply(
                lambda r: f"+{r['mom_cost_pct']:.1f}%" if pd.notna(r.get("mom_cost_pct")) and r.get("mom_diff_cost", 0) >= 0 else (f"{r['mom_cost_pct']:.1f}%" if pd.notna(r.get("mom_cost_pct")) else "-"),
                axis=1
            )
            disp_mom_df["mom_hours_str"] = disp_mom_df.apply(
                lambda r: f"+{r['mom_hours_pct']:.1f}%" if pd.notna(r.get("mom_hours_pct")) and r.get("mom_diff_hours", 0) >= 0 else (f"{r['mom_hours_pct']:.1f}%" if pd.notna(r.get("mom_hours_pct")) else "-"),
                axis=1
            )

            disp_mom_df = disp_mom_df[[
                "year_month", "total_cost", "base_cost", "overtime_premium", "mom_cost_str",
                "total_hours", "overtime_hours", "mom_hours_str", "worker_count", "task_count"
            ]]
            disp_mom_df.columns = [
                "월(YYYY-MM)", "최종 청구금액(원)", "기본금액(원)", "할증가산액(원)", "MoM 금액증감(%)",
                "총 인정공수(h)", "야간·주말(h)", "MoM 공수증감(%)", "투입인원", "작업건수"
            ]

            st.dataframe(
                disp_mom_df.style.format({
                    "최종 청구금액(원)": "₩ {:,.0f}",
                    "기본금액(원)": "₩ {:,.0f}",
                    "할증가산액(원)": "+₩ {:,.0f}",
                    "총 인정공수(h)": "{:,.1f}h",
                    "야간·주말(h)": "{:,.1f}h",
                    "투입인원": "{:,}명",
                    "작업건수": "{:,}건"
                }),
                use_container_width=True,
                height=220,
                hide_index=True
            )

            csv_mom_data = disp_mom_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="📥 월별 청구 추이 및 MoM 분석 CSV 다운로드",
                data=csv_mom_data,
                file_name=f"월별청구추이_MoM분석_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                key="btn_dl_mom_trend_csv"
            )

    # =========================================================
    # 탭 2: 업무 시간 직접 수정 장표 (크리티컬 기능)
    # =========================================================
    elif curr_page == "✏️ 업무 시간 직접 수정 장표":
        st.markdown('<div class="cost-table-header-cisco"><span>✏️</span><span>업무 시간 직접 수정 장표 (DB 영구 보존 오버라이드)</span></div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="cost-info-box-cisco">
            💡 <b>시간 직접 수정 가이드:</b> 아웃룩에서 사전 예정 시간이 정해지지 않아 <b>'종일(9.0h)'</b>로 등록되었거나 카카오톡 보고 시간이 잘못된 작업을 검토하여 실제 청구할 인정 공수(h)를 <b>직접 입력</b>하여 수정합니다. 여기서 수정한 공수는 수집기가 10분마다 다시 실행되더라도 <b>영구 보존</b>됩니다.
        </div>
        """, unsafe_allow_html=True)

        if df_calc.empty:
            st.info("선택된 조회 조건에 해당하는 '완료' 작업 데이터가 없습니다. (진행 중인 작업은 완료 보고 후 본 장표에 표출됩니다)")
        else:
            f_col1, f_col2, f_col3 = st.columns([4, 3, 3])
            with f_col1:
                only_allday = st.checkbox(
                    "☀️ [종일(9.0h) 등록 작업만 필터링]",
                    value=False,
                    help="아웃룩 종일 일정 등 9.0h로 등록되어 정산 검토가 필요한 작업만 모아봅니다.",
                    key="chk_filter_allday"
                )
            with f_col2:
                w_list = ["전체"] + sorted(df_calc["worker_name"].dropna().unique().tolist())
                sel_worker_adj = st.selectbox("👤 작업자 필터:", options=w_list, index=0, key="sb_adj_worker")
            with f_col3:
                search_kw = st.text_input("🔍 고객사 / 작업내용 검색:", placeholder="검색어 입력...", key="txt_adj_search")

            df_edit_src = df_calc.copy()

            # 🛡️ 이미 완료(COMPLETED)된 작업만 표출 (진행 중 PENDING/SCHEDULED 작업 배제)
            if "status" in df_edit_src.columns:
                comp_mask = df_edit_src["status"].astype(str).str.upper().isin(["COMPLETED", "완료"])
                df_edit_src = df_edit_src[comp_mask]

            if only_allday:
                df_edit_src = df_edit_src[df_edit_src["billable_hours"] >= 9.0]

            if sel_worker_adj != "전체":
                df_edit_src = df_edit_src[df_edit_src["worker_name"] == sel_worker_adj]

            if search_kw:
                kw = search_kw.strip().lower()
                c_mask = df_edit_src["client_name"].astype(str).str.lower().str.contains(kw, na=False)
                t_mask = df_edit_src["task_description"].astype(str).str.lower().str.contains(kw, na=False)
                df_edit_src = df_edit_src[c_mask | t_mask]

            if "start_time" in df_edit_src.columns:
                df_edit_src = df_edit_src.sort_values(by="start_time", ascending=False)

            st.caption(f"검색/필터 결과: 총 **{len(df_edit_src)}**건의 작업 (✅ 완료된 작업 기준)")

            if df_edit_src.empty:
                st.info("조회 조건에 해당하는 '완료' 작업 데이터가 없습니다. (진행 중인 작업은 완료 보고 후 본 장표에 표출됩니다)")
            else:
                # 1) msg_hash 안전 추출
                if "msg_hash" in df_edit_src.columns:
                    mh_series = df_edit_src["msg_hash"].astype(str)
                elif "id" in df_edit_src.columns:
                    mh_series = df_edit_src["id"].astype(str)
                else:
                    mh_series = df_edit_src.index.astype(str)

                # 2) 일자 포맷
                if "start_time" in df_edit_src.columns:
                    date_series = pd.to_datetime(df_edit_src["start_time"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M").fillna("-")
                else:
                    date_series = pd.Series("-", index=df_edit_src.index)

                # 3) 작업자/직급/고객사/작업내용/출처
                worker_series = df_edit_src["worker_name"].fillna("미지정").astype(str) if "worker_name" in df_edit_src.columns else pd.Series("미지정", index=df_edit_src.index)
                title_series = df_edit_src["worker_title"].fillna("기타").astype(str) if "worker_title" in df_edit_src.columns else pd.Series("기타", index=df_edit_src.index)
                client_series = df_edit_src["client_name"].fillna("기타").astype(str) if "client_name" in df_edit_src.columns else pd.Series("기타", index=df_edit_src.index)
                desc_series = df_edit_src["task_description"].fillna("").astype(str) if "task_description" in df_edit_src.columns else pd.Series("", index=df_edit_src.index)
                source_series = mh_series.apply(lambda x: "📅 아웃룩" if str(x).startswith("OUTLOOK_") else "💬 카카오톡")

                # 4) 공수 및 비고 (결측치 및 컬럼 부재 안전 처리)
                if "original_hours" in df_edit_src.columns:
                    orig_h_series = pd.to_numeric(df_edit_src["original_hours"], errors="coerce").fillna(df_edit_src["billable_hours"]).round(1)
                else:
                    orig_h_series = pd.to_numeric(df_edit_src["billable_hours"], errors="coerce").fillna(0.0).round(1)

                adj_h_series = pd.to_numeric(df_edit_src["billable_hours"], errors="coerce").fillna(0.0).round(1)

                if "note" in df_edit_src.columns:
                    note_series = df_edit_src["note"].fillna("").astype(str)
                else:
                    note_series = pd.Series("", index=df_edit_src.index)

                edit_df = pd.DataFrame({
                    "msg_hash": mh_series,
                    "일자": date_series,
                    "작업자": worker_series,
                    "직급": title_series,
                    "고객사": client_series,
                    "작업내용": desc_series,
                    "출처": source_series,
                    "기존공수(h)": orig_h_series,
                    "인정공수(h)": adj_h_series,
                    "비고": note_series
                }, index=df_edit_src.index)

                column_config = {
                    "msg_hash": None,
                    "일자": st.column_config.TextColumn("일자", disabled=True, width="medium"),
                    "작업자": st.column_config.TextColumn("작업자", disabled=True, width="small"),
                    "직급": st.column_config.TextColumn("직급", disabled=True, width="small"),
                    "고객사": st.column_config.TextColumn("고객사", disabled=True, width="medium"),
                    "작업내용": st.column_config.TextColumn("작업 내용", disabled=True, width="large"),
                    "출처": st.column_config.TextColumn("출처", disabled=True, width="small"),
                    "기존공수(h)": st.column_config.NumberColumn("기존공수", disabled=True, format="%.1f h", width="small"),
                    "인정공수(h)": st.column_config.NumberColumn(
                        "✏️ 인정공수(직접입력)",
                        help="실제 청구할 시간을 직접 입력하세요 (단위: 시간).",
                        min_value=0.0,
                        max_value=24.0,
                        step=0.5,
                        format="%.1f h",
                        required=True,
                        width="medium"
                    ),
                    "비고": st.column_config.TextColumn(
                        "수정 사유 / 비고",
                        help="수정 사유를 입력할 수 있습니다.",
                        width="medium"
                    )
                }

                edited_data = st.data_editor(
                    edit_df,
                    column_config=column_config,
                    column_order=["일자", "작업자", "직급", "고객사", "작업내용", "출처", "기존공수(h)", "인정공수(h)", "비고"],
                    disabled=["msg_hash", "일자", "작업자", "직급", "고객사", "작업내용", "출처", "기존공수(h)"],
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed",
                    key="editor_cost_adjust"
                )

                col_save_btn, col_save_info = st.columns([4, 6])
                with col_save_btn:
                    if st.button("💾 수정한 시간 일괄 DB 영구 저장", type="primary", use_container_width=True, key="btn_save_adjusted_hours"):
                        records_to_save = []
                        history_to_save = []
                        orig_map = dict(zip(edit_df["msg_hash"], zip(edit_df["인정공수(h)"], edit_df["비고"])))
                        current_user_name = AuthManager.get_current_user() or "관리자"

                        for _, row in edited_data.iterrows():
                            mh = row["msg_hash"]
                            new_h = float(row["인정공수(h)"])
                            new_note = str(row["비고"])
                            orig_h, orig_note = orig_map.get(mh, (new_h, new_note))

                            if abs(new_h - orig_h) > 0.01 or new_note != orig_note:
                                before_val = float(row["기존공수(h)"])
                                records_to_save.append({
                                    "msg_hash": mh,
                                    "adjusted_hours": new_h,
                                    "original_hours": before_val,
                                    "note": new_note
                                })
                                # 🕒 감사 이력(Audit Log) 레코드 동시 생성
                                history_to_save.append({
                                    "msg_hash": mh,
                                    "work_date": str(row["일자"]).split(" ")[0] if " " in str(row["일자"]) else str(row["일자"]),
                                    "worker_name": str(row["작업자"]),
                                    "client_name": str(row["고객사"]),
                                    "task_description": str(row["작업내용"]),
                                    "before_hours": before_val,
                                    "after_hours": new_h,
                                    "diff_hours": round(new_h - before_val, 2),
                                    "note": new_note,
                                    "adjusted_by": current_user_name
                                })

                        if not records_to_save:
                            st.info("💡 변경된 시간이 없습니다. 테이블의 '인정공수' 숫자를 직접 수정한 후 눌러주세요.")
                        else:
                            with st.spinner(f"총 {len(records_to_save)}건의 작업 시간 및 감사 이력을 DB에 영구 저장하는 중..."):
                                count = CostEstimationService.batch_update_work_log_hours(records_to_save)
                                if history_to_save:
                                    CostEstimationService.save_adjust_history(history_to_save)
                                st.success(f"🎉 총 {count}건의 작업 인정 공수 및 감사 이력이 성공적으로 영구 저장되었습니다!")
                                st.toast(f"✅ {count}건 시간 수정 & 감사 로그 기록 완료! 통계가 자동 재계산됩니다.", icon="💾")
                                st.cache_data.clear()
                                st.rerun()

                with col_save_info:
                    st.markdown("""
                    <div style="font-size: 12px; color: #64748b; line-height: 1.6; padding-top: 4px;">
                        • 인정공수 셀을 더블클릭하거나 클릭 후 숫자를 직접 입력하세요. 수정 후 [💾 수정한 시간 일괄 DB 영구 저장] 버튼을 누르면 실시간 반영 및 감사 로그에 기록됩니다.
                    </div>
                    """, unsafe_allow_html=True)

    # =========================================================
    # 탭 4: 🕒 시간 수정 감사 이력 (Audit Trail Timeline)
    # =========================================================
    elif curr_page == "🕒 시간 수정 감사 이력":
        st.markdown('<div class="cost-table-header-cisco"><span>🕒</span><span>인정 공수 시간 수정 감사 이력 타임라인 (Audit Trail)</span></div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="cost-info-box-cisco">
            💡 <b>감사 이력 가이드:</b> 인정 공수가 수정된 모든 작업 내역의 변경 전후 공수, 변동폭(±h), 수정 사유, 수정자 및 수정 일시를 영구 보존하며 투명하게 추적합니다.
        </div>
        """, unsafe_allow_html=True)

        history_df = CostEstimationService.get_adjust_history(limit=500)

        if history_df.empty:
            st.info("기록된 시간 수정 감사 이력이 없습니다. (업무 시간 직접 수정 장표에서 시간을 수정한 내역이 자동으로 기록됩니다)")
        else:
            total_logs = len(history_df)
            net_diff_hours = float(history_df["diff_hours"].sum()) if "diff_hours" in history_df.columns else 0.0
            unique_workers = history_df["worker_name"].nunique() if "worker_name" in history_df.columns else 0

            latest_ts_raw = history_df["created_at"].iloc[0] if "created_at" in history_df.columns and not history_df.empty else "-"
            if latest_ts_raw != "-" and pd.notna(latest_ts_raw):
                try:
                    latest_ts = pd.to_datetime(latest_ts_raw).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    latest_ts = str(latest_ts_raw)[:16]
            else:
                latest_ts = "-"

            diff_color = "#10b981" if net_diff_hours >= 0 else "#ef4444"
            diff_sign = "+" if net_diff_hours > 0 else ""

            st.markdown(f"""
            <div class="cost-kpi-row">
                <div class="cost-kpi-card-white top-navy">
                    <div class="cost-kpi-label-gray">📋 총 감사 이력 건수</div>
                    <div class="cost-kpi-val-bold" style="color: #005073;">{total_logs:,}건</div>
                    <div class="cost-kpi-sub-text" style="color: #0284c7;">누적 공수 수정 트랜잭션</div>
                </div>
                <div class="cost-kpi-card-white top-blue">
                    <div class="cost-kpi-label-gray">⚖️ 순 누적 공수 변동폭</div>
                    <div class="cost-kpi-val-bold" style="color: {diff_color};">{diff_sign}{net_diff_hours:,.1f} h</div>
                    <div class="cost-kpi-sub-text" style="color: {diff_color};">수정 전후 인정 시간 순증감</div>
                </div>
                <div class="cost-kpi-card-white top-green">
                    <div class="cost-kpi-label-gray">👤 수정 대상 작업자</div>
                    <div class="cost-kpi-val-bold" style="color: #10b981;">{unique_workers}명</div>
                    <div class="cost-kpi-sub-text" style="color: #64748b;">시간 보정 발생 인력</div>
                </div>
                <div class="cost-kpi-card-white top-purple">
                    <div class="cost-kpi-label-gray">⏱️ 최근 수정 일시</div>
                    <div class="cost-kpi-val-bold" style="color: #8b5cf6; font-size: 20px !important;">{latest_ts}</div>
                    <div class="cost-kpi-sub-text" style="color: #8b5cf6;">최신 감사 로그 기록 시점</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            fc1, fc2, fc3 = st.columns([3, 3, 4])
            with fc1:
                hist_workers = ["전체"] + sorted(history_df["worker_name"].dropna().unique().tolist()) if "worker_name" in history_df.columns else ["전체"]
                sel_hw = st.selectbox("👤 작업자 필터:", options=hist_workers, key="sb_hist_worker")
            with fc2:
                hist_clients = ["전체"] + sorted(history_df["client_name"].dropna().unique().tolist()) if "client_name" in history_df.columns else ["전체"]
                sel_hc = st.selectbox("🏢 고객사 필터:", options=hist_clients, key="sb_hist_client")
            with fc3:
                search_hist = st.text_input("🔍 작업내용 / 수정사유 검색:", placeholder="검색어 입력...", key="txt_hist_search")

            filt_df = history_df.copy()
            if sel_hw != "전체" and "worker_name" in filt_df.columns:
                filt_df = filt_df[filt_df["worker_name"] == sel_hw]
            if sel_hc != "전체" and "client_name" in filt_df.columns:
                filt_df = filt_df[filt_df["client_name"] == sel_hc]
            if search_hist:
                kw = search_hist.strip().lower()
                m1 = filt_df["task_description"].astype(str).str.lower().str.contains(kw, na=False) if "task_description" in filt_df.columns else pd.Series(False, index=filt_df.index)
                m2 = filt_df["note"].astype(str).str.lower().str.contains(kw, na=False) if "note" in filt_df.columns else pd.Series(False, index=filt_df.index)
                filt_df = filt_df[m1 | m2]

            st.caption(f"감사 로그 조회 결과: 총 **{len(filt_df)}**건 (최신순)")

            if filt_df.empty:
                st.info("검색/필터 조건에 일치하는 감사 이력이 없습니다.")
            else:
                disp_hist = filt_df.copy()
                if "created_at" in disp_hist.columns:
                    disp_hist["수정일시"] = pd.to_datetime(disp_hist["created_at"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M").fillna("-")
                else:
                    disp_hist["수정일시"] = "-"

                disp_hist["작업일자"] = disp_hist.get("work_date", pd.Series("-", index=disp_hist.index)).fillna("-")
                disp_hist["작업자"] = disp_hist.get("worker_name", pd.Series("-", index=disp_hist.index)).fillna("-")
                disp_hist["고객사"] = disp_hist.get("client_name", pd.Series("-", index=disp_hist.index)).fillna("-")
                disp_hist["작업내용"] = disp_hist.get("task_description", pd.Series("", index=disp_hist.index)).fillna("")
                disp_hist["수정전(h)"] = pd.to_numeric(disp_hist.get("before_hours", 0.0), errors="coerce").fillna(0.0).round(1)
                disp_hist["수정후(h)"] = pd.to_numeric(disp_hist.get("after_hours", 0.0), errors="coerce").fillna(0.0).round(1)
                disp_hist["변동폭(h)"] = pd.to_numeric(disp_hist.get("diff_hours", 0.0), errors="coerce").fillna(0.0).round(1)
                disp_hist["변동폭(표기)"] = disp_hist["변동폭(h)"].apply(lambda v: f"+{v:.1f}h" if v > 0 else (f"{v:.1f}h" if v < 0 else "0.0h"))
                disp_hist["수정사유"] = disp_hist.get("note", pd.Series("", index=disp_hist.index)).fillna("")
                disp_hist["수정자"] = disp_hist.get("adjusted_by", pd.Series("관리자", index=disp_hist.index)).fillna("관리자")

                disp_cols = [
                    "수정일시", "작업일자", "작업자", "고객사", "작업내용",
                    "수정전(h)", "수정후(h)", "변동폭(표기)", "수정사유", "수정자"
                ]
                final_hist_disp = disp_hist[disp_cols].copy()

                st.dataframe(
                    final_hist_disp.style.format({
                        "수정전(h)": "{:,.1f}h",
                        "수정후(h)": "{:,.1f}h"
                    }),
                    column_config={
                        "수정일시": st.column_config.TextColumn("수정일시", width="medium"),
                        "작업일자": st.column_config.TextColumn("작업일자", width="small"),
                        "작업자": st.column_config.TextColumn("작업자", width="small"),
                        "고객사": st.column_config.TextColumn("고객사", width="medium"),
                        "작업내용": st.column_config.TextColumn("작업내용", width="large"),
                        "수정전(h)": st.column_config.NumberColumn("수정 전", format="%.1f h", width="small"),
                        "수정후(h)": st.column_config.NumberColumn("수정 후", format="%.1f h", width="small"),
                        "변동폭(표기)": st.column_config.TextColumn("변동폭", width="small"),
                        "수정사유": st.column_config.TextColumn("수정 사유", width="medium"),
                        "수정자": st.column_config.TextColumn("수정자", width="small")
                    },
                    use_container_width=True,
                    height=420,
                    hide_index=True
                )

                csv_hist = final_hist_disp.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 시간 수정 감사 이력 CSV 다운로드",
                    data=csv_hist,
                    file_name=f"시간수정_감사이력_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key="btn_dl_audit_history_csv"
                )

    # =========================================================
    # 탭 5: 직급별 시간당 단가 설정
    # =========================================================
    elif curr_page == "⚙️ 직급별 시간당 단가 설정":
        st.markdown('<div class="cost-table-header-cisco"><span>⚙️</span><span>직급별 시간당 지원 금액(단가) 설정</span></div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="cost-info-box-cisco">
            💡 <b>단가 관리 가이드:</b> 사업본부에 청구할 직급별 시간당 단가(원/h)를 설정합니다. 단가는 언제든 수정 가능하며, DB에 영구 저장되어 모든 비용 계산에 즉시 반영됩니다.
        </div>
        """, unsafe_allow_html=True)

        current_rates = CostEstimationService.get_hourly_rates()

        title_cards = [
            {"title": "수석", "badge_color": "#005073", "border_color": "#005073", "icon": "👑", "tag": "수석"},
            {"title": "과장", "badge_color": "#0284c7", "border_color": "#0284c7", "icon": "💼", "tag": "과장"},
            {"title": "대리", "badge_color": "#10b981", "border_color": "#10b981", "icon": "⚡", "tag": "대리"},
            {"title": "사원", "badge_color": "#8b5cf6", "border_color": "#8b5cf6", "icon": "🌱", "tag": "사원"}
        ]

        with st.form("form_hourly_rates_settings"):
            st.markdown("""
            <div style="margin-bottom: 14px; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px;">
                <span style="font-size: 17px; font-weight: 900; color: #000000; letter-spacing: -0.3px;">👔 4대 표준 직급별 시간당 지원 단가 (원 / 시간)</span>
                <span style="font-size: 12.5px; color: #475569; margin-left: 8px; font-weight: 600;">각 직급의 1시간당 청구 금액을 설정합니다.</span>
            </div>
            """, unsafe_allow_html=True)
            
            rate_inputs = {}
            cols = st.columns(4)

            for idx, c_info in enumerate(title_cards):
                t = c_info["title"]
                val = current_rates.get(t, 50000)
                with cols[idx]:
                    st.markdown(f"""
                    <div style="background: #ffffff; border: 1.5px solid #cbd5e1; border-top: 6px solid {c_info['badge_color']}; border-radius: 10px; padding: 12px 14px 10px 14px; box-shadow: 0 2px 6px rgba(0,0,0,0.04); margin-bottom: 8px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                            <span style="font-size: 22px; font-weight: 900; color: #000000; letter-spacing: -0.5px;">{c_info['icon']} {t}</span>
                            <span style="background: {c_info['badge_color']}; color: #ffffff; font-size: 11px; font-weight: 800; padding: 2px 7px; border-radius: 4px;">{c_info['tag']}</span>
                        </div>
                        <div style="font-size: 12px; font-weight: 800; color: #000000; margin-top: 2px;">
                            시간당 단가 (원/h)
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    rate_inputs[t] = st.number_input(
                        f"{t} 단가",
                        min_value=0,
                        max_value=1000000,
                        value=int(val),
                        step=5000,
                        format="%d",
                        key=f"input_rate_{t}",
                        label_visibility="collapsed"
                    )

            st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
            btn_submit_rates = st.form_submit_button("💾 4대 직급 단가 일괄 저장 (DB 영구 보존)", type="primary", use_container_width=True)

            if btn_submit_rates:
                ordered_titles = [c["title"] for c in title_cards]
                updated_rates = {t: int(rate_inputs[t]) for t in ordered_titles}
                success = CostEstimationService.save_hourly_rates(updated_rates)
                if success:
                    st.success("🎉 4대 직급 시간당 단가가 성공적으로 저장되었습니다!")
                    st.toast("✅ 단가 저장 완료! 예상 비용이 실시간으로 재계산됩니다.", icon="💰")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("단가 저장 중 오류가 발생했습니다.")
