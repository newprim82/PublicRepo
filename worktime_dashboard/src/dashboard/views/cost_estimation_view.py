import io
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from ...services.cost_estimation_service import CostEstimationService
from ...services.team_service import TeamService, UNASSIGNED_TEAM
from ..common.ui_helpers import get_job_title_badge, get_job_title_color, get_job_title_rank


def render_cost_estimation_view(
    df: pd.DataFrame,
    df_raw: pd.DataFrame,
    selected_team: str,
    team_mappings: dict,
    month_desc: str = "",
    worker_desc: str = "",
    extra_chips_str: str = "",
    curr_page: str = "💰 예상 비용산정"
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

    /* 2. 상단 필터 요약 박스 */
    .cost-filter-summary-card {
        background: #ffffff !important;
        border: 1.5px solid #cbd5e1 !important;
        border-radius: 8px !important;
        padding: 8px 14px !important;
        text-align: right !important;
        font-size: 12.5px !important;
        color: #334155 !important;
        box-shadow: 0 1px 4px rgba(0, 45, 66, 0.05) !important;
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
    </style>
    """, unsafe_allow_html=True)

    # 1. 계산된 예상 비용 데이터프레임 도출
    df_calc = CostEstimationService.calculate_costs(df)
    kpis = CostEstimationService.get_cost_summary_kpis(df_calc)

    # 페이지별 타이틀 및 설명 동적 매핑
    page_titles = {
        "💰 팀원별 예상 청구금액": ("💰", "팀원별 프로젝트/지원 예상 청구금액", "기술본부 인력별 투입 공수 및 직급별 단가를 기준으로 사업본부 청구 금액을 산출합니다."),
        "💰 예상 비용산정": ("💰", "팀원별 프로젝트/지원 예상 청구금액", "기술본부 인력별 투입 공수 및 직급별 단가를 기준으로 사업본부 청구 금액을 산출합니다."),
        "💰 예상 비용산정 대시보드": ("💰", "팀원별 프로젝트/지원 예상 청구금액", "기술본부 인력별 투입 공수 및 직급별 단가를 기준으로 사업본부 청구 금액을 산출합니다."),
        "🏢 고객사별 청구 금액": ("🏢", "고객사별 프로젝트/지원 예상 청구 금액", "고객사 및 프로젝트별 투입 공수(h)와 총 청구 예상 금액을 집계 분석합니다."),
        "✏️ 업무 시간 직접 수정 장표": ("✏️", "업무 시간 직접 수정 장표", "아웃룩 '종일(9.0h)' 등록 작업 및 지원 공수를 직접 검토하고 영구 수정합니다."),
        "⚙️ 직급별 시간당 단가 설정": ("⚙️", "직급별 시간당 단가 설정", "사업본부 청구용 직급별 시간당 단가(원/h)를 설정하고 DB에 영구 저장합니다.")
    }
    icon, title_txt, desc_txt = page_titles.get(curr_page, ("💰", "프로젝트/현장지원 예상 비용산정", "기술본부 인력의 투입 공수 및 직급별 단가를 기준으로 예상 청구 금액을 산출합니다."))

    # 2. 상단 헤더 및 조회 기준 요약 배지 바 (선명한 다크 네이비 & 화이트 배지)
    col_t1, col_t2 = st.columns([7, 3])
    with col_t1:
        st.markdown(f"""
        <div style="margin-bottom: 14px;">
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
        period_text = month_desc if month_desc else "전체 기간"
        team_text = selected_team if selected_team else "전체 팀"
        worker_text = worker_desc if worker_desc else "전체 인원"
        st.markdown(f"""
        <div class="cost-filter-summary-card">
            <div>📅 <b>기간:</b> <span style="color: #005073; font-weight: 800;">{period_text}</span></div>
            <div style="margin-top: 3px;">🏢 <b>대상:</b> <span style="color: #0284c7; font-weight: 800;">{team_text}</span> | <span style="color: #6366f1; font-weight: 700;">{worker_text}</span></div>
        </div>
        """, unsafe_allow_html=True)

    # 3. 상단 4대 메트릭 화이트 펄스 카드
    tot_cost_str = f"₩ {kpis['total_cost']:,}"
    tot_hours_str = f"{kpis['total_billable_hours']:,.1f} h"
    adj_pct = (kpis['adjusted_count'] / max(1, kpis['total_tasks'])) * 100

    st.markdown(f"""
    <div class="cost-kpi-row">
        <div class="cost-kpi-card-white top-navy">
            <div class="cost-kpi-label-gray">💳 총 예상 청구금액</div>
            <div class="cost-kpi-val-bold" style="color: #005073;">{tot_cost_str}</div>
            <div class="cost-kpi-sub-text" style="color: #0284c7;">총 {kpis['total_tasks']:,}건 작업 기준</div>
        </div>
        <div class="cost-kpi-card-white top-blue">
            <div class="cost-kpi-label-gray">⏱️ 총 투입 인정 공수</div>
            <div class="cost-kpi-val-bold" style="color: #0284c7;">{tot_hours_str}</div>
            <div class="cost-kpi-sub-text" style="color: #10b981;">휴가 0h 제외 실제 청구 공수</div>
        </div>
        <div class="cost-kpi-card-white top-green">
            <div class="cost-kpi-label-gray">👥 투입 인력 / 평균 단가</div>
            <div class="cost-kpi-val-bold" style="color: #10b981;">{kpis['worker_count']}명</div>
            <div class="cost-kpi-sub-text" style="color: #64748b;">가중평균 {kpis['avg_hourly_rate']:,}원/h</div>
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
    if curr_page in ["💰 팀원별 예상 청구금액", "💰 예상 비용산정", "💰 예상 비용산정 대시보드"]:
        st.markdown('<div class="cost-table-header-cisco"><span>👤</span><span>팀원별 투입 공수 및 예상 청구 금액 정산표</span></div>', unsafe_allow_html=True)

        worker_df = CostEstimationService.get_worker_cost_summary(df_calc)
        if worker_df.empty:
            st.info("조회 기준에 해당하는 팀원 작업 데이터가 없습니다.")
        else:
            col_w1, col_w2 = st.columns([6, 4])
            with col_w1:
                display_worker_df = worker_df.copy()
                display_worker_df.columns = [
                    "팀원명", "소속팀", "직급", "시간당 단가(원)", "인정 공수(h)", "예상 청구금액(원)", "작업 건수", "보정 건수"
                ]

                st.dataframe(
                    display_worker_df.style.format({
                        "시간당 단가(원)": "{:,.0f}원",
                        "인정 공수(h)": "{:,.1f}h",
                        "예상 청구금액(원)": "₩ {:,.0f}",
                        "작업 건수": "{:,}건",
                        "보정 건수": "{:,}건"
                    }),
                    use_container_width=True,
                    height=360
                )

                csv_data = display_worker_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 팀원별 정산표 CSV 다운로드",
                    data=csv_data,
                    file_name=f"팀원별_예상청구비용_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key="btn_dl_worker_cost_csv"
                )

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

        st.markdown('<div class="cost-table-header-cisco" style="margin-top: 20px;"><span>👔</span><span>직급별 공수 및 청구 금액 점유율</span></div>', unsafe_allow_html=True)
        title_df = CostEstimationService.get_title_cost_summary(df_calc)
        if not title_df.empty:
            col_t_tab1, col_t_tab2 = st.columns([6, 4])
            with col_t_tab1:
                disp_title_df = title_df.copy()
                disp_title_df.columns = ["직급", "단가(원/h)", "투입인원", "총 인정공수(h)", "예상 청구금액(원)", "작업건수", "금액 점유율(%)"]
                st.dataframe(
                    disp_title_df.style.format({
                        "단가(원/h)": "{:,.0f}원",
                        "투입인원": "{:,}명",
                        "총 인정공수(h)": "{:,.1f}h",
                        "예상 청구금액(원)": "₩ {:,.0f}",
                        "작업건수": "{:,}건",
                        "금액 점유율(%)": "{:.1f}%"
                    }),
                    use_container_width=True,
                    height=240
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

    # =========================================================
    # 탭 2: 고객사별 청구 금액
    # =========================================================
    elif curr_page == "🏢 고객사별 청구 금액":
        st.markdown('<div class="cost-table-header-cisco"><span>🏢</span><span>고객사/프로젝트별 예상 청구 금액 정산표</span></div>', unsafe_allow_html=True)
        client_df = CostEstimationService.get_client_cost_summary(df_calc)
        if client_df.empty:
            st.info("조회 기준에 해당하는 고객사 작업 데이터가 없습니다.")
        else:
            col_c1, col_c2 = st.columns([6, 4])
            with col_c1:
                disp_client_df = client_df.copy()
                disp_client_df.columns = ["고객사명", "투입 인원수", "총 인정 공수(h)", "예상 청구금액(원)", "작업 건수", "보정 건수"]
                st.dataframe(
                    disp_client_df.style.format({
                        "투입 인원수": "{:,}명",
                        "총 인정 공수(h)": "{:,.1f}h",
                        "예상 청구금액(원)": "₩ {:,.0f}",
                        "작업 건수": "{:,}건",
                        "보정 건수": "{:,}건"
                    }),
                    use_container_width=True,
                    height=380
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

    # =========================================================
    # 탭 3: 업무 시간 직접 수정 장표 (크리티컬 기능)
    # =========================================================
    elif curr_page == "✏️ 업무 시간 직접 수정 장표":
        st.markdown('<div class="cost-table-header-cisco"><span>✏️</span><span>업무 시간 직접 수정 장표 (DB 영구 보존 오버라이드)</span></div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="cost-info-box-cisco">
            💡 <b>시간 직접 수정 가이드:</b> 아웃룩에서 사전 예정 시간이 정해지지 않아 <b>'종일(9.0h)'</b>로 등록되었거나 카카오톡 보고 시간이 잘못된 작업을 검토하여 실제 청구할 인정 공수(h)를 <b>직접 입력</b>하여 수정합니다.<br>
            여기서 수정한 공수는 수집기가 10분마다 다시 실행되더라도 <b>영구 보존</b>됩니다.
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
                        orig_map = dict(zip(edit_df["msg_hash"], zip(edit_df["인정공수(h)"], edit_df["비고"])))

                        for _, row in edited_data.iterrows():
                            mh = row["msg_hash"]
                            new_h = float(row["인정공수(h)"])
                            new_note = str(row["비고"])
                            orig_h, orig_note = orig_map.get(mh, (new_h, new_note))

                            if abs(new_h - orig_h) > 0.01 or new_note != orig_note:
                                records_to_save.append({
                                    "msg_hash": mh,
                                    "adjusted_hours": new_h,
                                    "original_hours": float(row["기존공수(h)"]),
                                    "note": new_note
                                })

                        if not records_to_save:
                            st.info("💡 변경된 시간이 없습니다. 테이블의 '인정공수' 숫자를 직접 수정한 후 눌러주세요.")
                        else:
                            with st.spinner(f"총 {len(records_to_save)}건의 작업 시간을 DB에 영구 저장하는 중..."):
                                count = CostEstimationService.batch_update_work_log_hours(records_to_save)
                                st.success(f"🎉 총 {count}건의 작업 인정 공수가 성공적으로 영구 저장되었습니다!")
                                st.toast(f"✅ {count}건 시간 수정 완료! 통계가 자동 재계산됩니다.", icon="💾")
                                st.cache_data.clear()
                                st.rerun()

                with col_save_info:
                    st.markdown("""
                    <div style="font-size: 12px; color: #64748b; line-height: 1.6; padding-top: 4px;">
                        • 인정공수 셀을 더블클릭하거나 클릭 후 숫자를 직접 입력하세요.<br>
                        • 수정 후 위의 [💾 수정한 시간 일괄 DB 영구 저장] 버튼을 누르면 실시간 반영됩니다.
                    </div>
                    """, unsafe_allow_html=True)

    # =========================================================
    # 탭 4: 직급별 시간당 단가 설정
    # =========================================================
    elif curr_page == "⚙️ 직급별 시간당 단가 설정":
        st.markdown('<div class="cost-table-header-cisco"><span>⚙️</span><span>직급별 시간당 지원 금액(단가) 설정</span></div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="cost-info-box-cisco">
            💡 <b>단가 관리 가이드:</b> 사업본부에 청구할 직급별 시간당 단가(원/h)를 설정합니다.<br>
            단가는 언제든 수정 가능하며, DB에 영구 저장되어 모든 비용 계산에 즉시 반영됩니다.
        </div>
        """, unsafe_allow_html=True)

        current_rates = CostEstimationService.get_hourly_rates()

        with st.form("form_hourly_rates_settings"):
            st.markdown("<h5 style='color: #002d42; font-weight: 800;'>👔 직급별 시간당 단가 (원 / 시간)</h5>", unsafe_allow_html=True)
            
            rate_inputs = {}
            ordered_titles = ["수석", "차장", "과장", "대리", "사원", "기타"]
            for t in current_rates.keys():
                if t not in ordered_titles:
                    ordered_titles.append(t)

            cols_per_row = 3
            rows = [ordered_titles[i:i + cols_per_row] for i in range(0, len(ordered_titles), cols_per_row)]

            for row_titles in rows:
                cols = st.columns(len(row_titles))
                for idx, t in enumerate(row_titles):
                    with cols[idx]:
                        val = current_rates.get(t, 50000)
                        rate_inputs[t] = st.number_input(
                            f"👔 {t} 단가 (원/h):",
                            min_value=0,
                            max_value=1000000,
                            value=int(val),
                            step=5000,
                            format="%d",
                            key=f"input_rate_{t}"
                        )

            st.markdown("<hr style='margin: 15px 0; border-color: #cbd5e1;'>", unsafe_allow_html=True)
            st.markdown("<h5 style='color: #002d42; font-weight: 800;'>➕ 신규 직급 단가 추가 (선택)</h5>", unsafe_allow_html=True)
            c_new1, c_new2 = st.columns(2)
            with c_new1:
                new_title_name = st.text_input("새 직급명 (예: 인턴, 고문 등):", key="txt_new_title_rate")
            with c_new2:
                new_title_rate = st.number_input("새 직급 시간당 단가 (원/h):", min_value=0, max_value=1000000, value=40000, step=5000, format="%d", key="num_new_title_rate")

            btn_submit_rates = st.form_submit_button("💾 직급별 단가 설정 저장", type="primary", use_container_width=True)

            if btn_submit_rates:
                updated_rates = dict(rate_inputs)
                if new_title_name.strip():
                    updated_rates[new_title_name.strip()] = int(new_title_rate)

                success = CostEstimationService.save_hourly_rates(updated_rates)
                if success:
                    st.success("🎉 직급별 시간당 단가가 성공적으로 저장되었습니다!")
                    st.toast("✅ 단가 저장 완료! 예상 비용이 실시간으로 재계산됩니다.", icon="💰")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("단가 저장 중 오류가 발생했습니다.")
