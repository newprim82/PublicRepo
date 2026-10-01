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
    💰 [예상 비용산정] 메인 관제 캔버스
    1. 직급별 시간당 단가 관리 (DB 저장, 변동 가능)
    2. 업무 시간 직접 수정 및 영구 보존 (아웃룩 '종일' 등 오버라이드)
    3. 조회 기준(기간, 팀, 팀원, 고객사) 연동 예상 청구 금액 산정
    4. 팀원별, 고객사별, 직급별 다차원 정산 대시보드
    """
    st.markdown("""
    <style>
    /* 예상 비용산정 전용 KPI 카드 스타일 */
    .cost-kpi-container {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 14px;
        margin-bottom: 22px;
    }
    @media (max-width: 900px) {
        .cost-kpi-container {
            grid-template-columns: repeat(2, 1fr);
        }
    }
    @media (max-width: 600px) {
        .cost-kpi-container {
            grid-template-columns: 1fr;
        }
    }
    .cost-kpi-card {
        background: linear-gradient(135deg, rgba(13, 27, 42, 0.85) 0%, rgba(20, 40, 65, 0.75) 100%);
        border: 1px solid rgba(0, 180, 216, 0.35);
        border-radius: 10px;
        padding: 16px 18px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
        position: relative;
        overflow: hidden;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .cost-kpi-card:hover {
        transform: translateY(-2px);
        border-color: #00e5ff;
    }
    .cost-kpi-card::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 4px;
        height: 100%;
        background: #00b4d8;
    }
    .cost-kpi-card.accent-gold::before {
        background: #ffd166;
    }
    .cost-kpi-card.accent-green::before {
        background: #06d6a0;
    }
    .cost-kpi-card.accent-purple::before {
        background: #b5179e;
    }
    .cost-kpi-label {
        font-size: 12.5px;
        color: #94a3b8;
        font-weight: 700;
        letter-spacing: 0.3px;
        margin-bottom: 6px;
    }
    .cost-kpi-value {
        font-size: 24px;
        font-weight: 800;
        color: #ffffff;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
    }
    .cost-kpi-sub {
        font-size: 11.5px;
        color: #00e5ff;
        margin-top: 5px;
        font-weight: 600;
    }

    /* 테이블 헤더 커스텀 */
    .cost-table-header {
        background: rgba(0, 180, 216, 0.12);
        border-left: 3px solid #00b4d8;
        padding: 8px 12px;
        border-radius: 4px;
        margin-bottom: 10px;
        font-size: 14px;
        font-weight: 700;
        color: #ffffff;
    }
    </style>
    """, unsafe_allow_html=True)

    # 1. 계산된 예상 비용 데이터프레임 도출
    df_calc = CostEstimationService.calculate_costs(df)
    kpis = CostEstimationService.get_cost_summary_kpis(df_calc)

    # 2. 상단 헤더 및 조회 기준 요약 배지 바
    col_t1, col_t2 = st.columns([7, 3])
    with col_t1:
        st.markdown(f"""
        <div style="margin-bottom: 12px;">
            <div style="font-size: 20px; font-weight: 800; color: #ffffff; display: flex; align-items: center; gap: 8px;">
                <span>💰 프로젝트/현장지원 예상 비용산정</span>
            </div>
            <div style="font-size: 12.5px; color: #94a3b8; margin-top: 4px;">
                사업본부 청구용 시간당 지원 단가를 기반으로 예상 청구 금액을 산출하고, 인정 공수를 직접 검토·수정합니다.
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_t2:
        period_text = month_desc if month_desc else "전체 기간"
        team_text = selected_team if selected_team else "전체 팀"
        worker_text = worker_desc if worker_desc else "전체 인원"
        st.markdown(f"""
        <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 8px 12px; text-align: right; font-size: 12px; color: #cbd5e1;">
            <div>📅 <b>기간:</b> <span style="color: #00e5ff;">{period_text}</span></div>
            <div style="margin-top: 2px;">🏢 <b>대상:</b> <span style="color: #38bdf8;">{team_text}</span> | <span style="color: #a78bfa;">{worker_text}</span></div>
        </div>
        """, unsafe_allow_html=True)

    # 3. 상단 4대 메트릭 KPI 카드
    tot_cost_str = f"₩ {kpis['total_cost']:,}"
    tot_hours_str = f"{kpis['total_billable_hours']:,.1f} h"
    worker_info_str = f"{kpis['worker_count']}명 (평균 {kpis['avg_hourly_rate']:,}원/h)"
    adj_info_str = f"{kpis['adjusted_count']}건 ({kpis['adjusted_count']/max(1, kpis['total_tasks'])*100:.1f}%)"

    st.markdown(f"""
    <div class="cost-kpi-container">
        <div class="cost-kpi-card accent-gold">
            <div class="cost-kpi-label">💳 총 예상 청구금액</div>
            <div class="cost-kpi-value" style="color: #ffd166;">{tot_cost_str}</div>
            <div class="cost-kpi-sub">총 {kpis['total_tasks']:,}건 작업 기준</div>
        </div>
        <div class="cost-kpi-card accent-green">
            <div class="cost-kpi-label">⏱️ 총 투입 인정 공수</div>
            <div class="cost-kpi-value" style="color: #06d6a0;">{tot_hours_str}</div>
            <div class="cost-kpi-sub">휴가 0h 제외 실제 청구 공수</div>
        </div>
        <div class="cost-kpi-card">
            <div class="cost-kpi-label">👥 투입 인력 / 평균 단가</div>
            <div class="cost-kpi-value">{kpis['worker_count']}명</div>
            <div class="cost-kpi-sub">가중평균 {kpis['avg_hourly_rate']:,}원/h</div>
        </div>
        <div class="cost-kpi-card accent-purple">
            <div class="cost-kpi-label">✏️ 시간 보정(수정) 작업</div>
            <div class="cost-kpi-value" style="color: #e0aaff;">{kpis['adjusted_count']}건</div>
            <div class="cost-kpi-sub">관리자 인정 공수 영구 오버라이드</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 4. 4대 세부 메뉴 탭 구성 (사이드바 서브메뉴와 완벽 연동)
    tab_options = [
        "👤 팀원/직급별 정산표",
        "🏢 고객사별 청구 금액",
        "✏️ 업무 시간 직접 수정 장표",
        "⚙️ 직급별 시간당 단가 설정"
    ]
    def_idx = 0
    if curr_page == "✏️ 업무 시간 직접 수정 장표":
        def_idx = 2
    elif curr_page == "⚙️ 직급별 시간당 단가 설정":
        def_idx = 3

    selected_sub_tab = st.radio(
        "정산 세부 메뉴 선택",
        options=tab_options,
        index=def_idx,
        horizontal=True,
        label_visibility="collapsed",
        key=f"cost_sub_tab_radio_{curr_page}"
    )
    st.markdown('<div style="height: 14px;"></div>', unsafe_allow_html=True)

    # =========================================================
    # 탭 1: 팀원/직급별 정산표
    # =========================================================
    if selected_sub_tab == "👤 팀원/직급별 정산표":
        st.markdown('<div class="cost-table-header">👤 팀원별 투입 공수 및 예상 청구 금액 정산표</div>', unsafe_allow_html=True)

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

                # 포맷팅
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

                # 엑셀 다운로드
                csv_data = display_worker_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 팀원별 정산표 CSV 다운로드",
                    data=csv_data,
                    file_name=f"팀원별_예상청구비용_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key="btn_dl_worker_cost_csv"
                )

            with col_w2:
                # 상위 10명 예상 청구 금액 바 차트
                top_workers = worker_df.head(10).sort_values(by="total_cost", ascending=True)
                fig_w = px.bar(
                    top_workers,
                    x="total_cost",
                    y="worker_name",
                    orientation="h",
                    text="total_cost",
                    title="🏆 예상 청구 금액 Top 10 팀원",
                    labels={"total_cost": "예상 청구금액 (원)", "worker_name": "팀원"},
                    color="total_cost",
                    color_continuous_scale="Blues"
                )
                fig_w.update_traces(texttemplate='₩ %{text:,.0f}', textposition='outside')
                fig_w.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    height=360,
                    margin=dict(l=20, r=40, t=40, b=20),
                    showlegend=False
                )
                st.plotly_chart(fig_w, use_container_width=True)

        # 직급별 요약 분포
        st.markdown('<div class="cost-table-header" style="margin-top: 20px;">👔 직급별 공수 및 청구 금액 점유율</div>', unsafe_allow_html=True)
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
                    color_discrete_sequence=px.colors.sequential.Teal
                )
                fig_t.update_traces(textposition='inside', textinfo='percent+label')
                fig_t.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    height=240,
                    margin=dict(l=10, r=10, t=35, b=10)
                )
                st.plotly_chart(fig_t, use_container_width=True)

    # =========================================================
    # 탭 2: 고객사별 청구 금액
    # =========================================================
    elif selected_sub_tab == "🏢 고객사별 청구 금액":
        st.markdown('<div class="cost-table-header">🏢 고객사/프로젝트별 예상 청구 금액 정산표</div>', unsafe_allow_html=True)
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
                    color_discrete_sequence=px.colors.qualitative.Prism
                )
                fig_c.update_traces(textposition='inside', textinfo='percent+label')
                fig_c.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    height=380,
                    margin=dict(l=10, r=10, t=40, b=20)
                )
                st.plotly_chart(fig_c, use_container_width=True)

    # =========================================================
    # 탭 3: 업무 시간 직접 수정 장표 (크리티컬 기능)
    # =========================================================
    elif selected_sub_tab == "✏️ 업무 시간 직접 수정 장표":
        st.markdown("""
        <div class="cost-table-header">
            ✏️ 업무 시간 직접 수정 장표 (DB 영구 보존 오버라이드)
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div style="font-size: 12.5px; color: #94a3b8; margin-bottom: 12px;">
            💡 <b>안내:</b> 아웃룩에서 사전 예정 시간이 정해지지 않아 <b>'종일(9.0h)'</b>로 등록되었거나 카카오톡 보고 시간이 잘못된 작업을 검토하여 실제 청구할 인정 공수(h)를 <b>직접 입력</b>하여 수정합니다. 여기서 수정한 공수는 수집기가 다시 실행되더라도 <b>영구 보존</b>됩니다.
        </div>
        """, unsafe_allow_html=True)

        if df_calc.empty:
            st.warning("수정할 대상 작업이 없습니다.")
        else:
            # 필터 툴바
            f_col1, f_col2, f_col3 = st.columns([4, 3, 3])
            with f_col1:
                only_allday = st.checkbox(
                    "☀️ [종일(9.0h) 등록 작업만 필터링]",
                    value=False,
                    help="아웃룩 종일 일정 등 9.0h로 등록되어 정산 검토가 필요한 작업만 모아봅니다.",
                    key="chk_filter_allday"
                )
            with f_col2:
                # 작업자 선택
                w_list = ["전체"] + sorted(df_calc["worker_name"].dropna().unique().tolist())
                sel_worker_adj = st.selectbox("👤 작업자 필터:", options=w_list, index=0, key="sb_adj_worker")
            with f_col3:
                search_kw = st.text_input("🔍 고객사 / 작업내용 검색:", placeholder="검색어 입력...", key="txt_adj_search")

            # 필터 적용
            df_edit_src = df_calc.copy()

            # 종일 필터
            if only_allday:
                df_edit_src = df_edit_src[df_edit_src["billable_hours"] >= 9.0]

            # 작업자 필터
            if sel_worker_adj != "전체":
                df_edit_src = df_edit_src[df_edit_src["worker_name"] == sel_worker_adj]

            # 키워드 검색
            if search_kw:
                kw = search_kw.strip().lower()
                c_mask = df_edit_src["client_name"].astype(str).str.lower().str.contains(kw, na=False)
                t_mask = df_edit_src["task_description"].astype(str).str.lower().str.contains(kw, na=False)
                df_edit_src = df_edit_src[c_mask | t_mask]

            # 날짜 정렬 (최신순)
            if "start_time" in df_edit_src.columns:
                df_edit_src = df_edit_src.sort_values(by="start_time", ascending=False)

            st.caption(f"검색/필터 결과: 총 **{len(df_edit_src)}**건의 작업")

            if df_edit_src.empty:
                st.info("조건에 일치하는 작업이 없습니다.")
            else:
                # data_editor용 데이터프레임 가공
                edit_df = pd.DataFrame()
                edit_df["msg_hash"] = df_edit_src["msg_hash"].astype(str)
                
                # 날짜 문자열
                if "start_time" in df_edit_src.columns:
                    edit_df["일자"] = pd.to_datetime(df_edit_src["start_time"]).dt.strftime("%Y-%m-%d %H:%M")
                else:
                    edit_df["일자"] = ""

                edit_df["작업자"] = df_edit_src["worker_name"].astype(str)
                edit_df["직급"] = df_edit_src["worker_title"].astype(str)
                edit_df["고객사"] = df_edit_src["client_name"].astype(str)
                edit_df["작업내용"] = df_edit_src["task_description"].astype(str)
                
                # 출처 표기
                edit_df["출처"] = df_edit_src["msg_hash"].apply(lambda x: "📅 아웃룩" if str(x).startswith("OUTLOOK_") else "💬 카카오톡")
                
                # 기존 공수 (읽기 전용 참조)
                edit_df["기존공수(h)"] = df_edit_src.get("original_hours", df_edit_src["billable_hours"]).round(1)

                # 수정할 인정 공수 (직접 입력 컬럼)
                edit_df["인정공수(h)"] = df_edit_src["billable_hours"].round(1)

                # 수정 사유 / 비고
                edit_df["비고"] = df_edit_src.get("note", "").fillna("").astype(str)

                # Streamlit data_editor 설정
                column_config = {
                    "msg_hash": None, # 숨김
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
                    disabled=["msg_hash", "일자", "작업자", "직급", "고객사", "작업내용", "출처", "기존공수(h)"],
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed",
                    key="editor_cost_adjust"
                )

                # 변경 감지 및 저장 버튼
                col_save_btn, col_save_info = st.columns([4, 6])
                with col_save_btn:
                    if st.button("💾 수정한 시간 일괄 DB 영구 저장", type="primary", use_container_width=True, key="btn_save_adjusted_hours"):
                        # 변경된 행 추출
                        records_to_save = []
                        orig_map = dict(zip(edit_df["msg_hash"], zip(edit_df["인정공수(h)"], edit_df["비고"])))

                        for _, row in edited_data.iterrows():
                            mh = row["msg_hash"]
                            new_h = float(row["인정공수(h)"])
                            new_note = str(row["비고"])
                            orig_h, orig_note = orig_map.get(mh, (new_h, new_note))

                            # 값이 달라졌거나 비고가 달라졌으면 저장 대상
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
                    <div style="font-size: 11.5px; color: #64748b; line-height: 1.6; padding-top: 4px;">
                        • 인정공수 셀을 더블클릭하거나 클릭 후 숫자를 직접 입력하세요.<br>
                        • 수정 후 위의 [💾 수정한 시간 일괄 DB 영구 저장] 버튼을 누르면 실시간 반영됩니다.
                    </div>
                    """, unsafe_allow_html=True)

    # =========================================================
    # 탭 4: 직급별 시간당 단가 설정
    # =========================================================
    elif selected_sub_tab == "⚙️ 직급별 시간당 단가 설정":
        st.markdown("""
        <div class="cost-table-header">
            ⚙️ 직급별 시간당 지원 금액(단가) 설정
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div style="font-size: 12.5px; color: #94a3b8; margin-bottom: 16px;">
            💡 사업본부에 청구할 직급별 시간당 단가(원/h)를 설정합니다. 단가는 언제든 수정 가능하며, DB에 영구 저장되어 모든 비용 계산에 즉시 반영됩니다.
        </div>
        """, unsafe_allow_html=True)

        current_rates = CostEstimationService.get_hourly_rates()

        with st.form("form_hourly_rates_settings"):
            st.markdown("##### 👔 직급별 시간당 단가 (원 / 시간)")
            
            rate_inputs = {}
            # 기본 직급 순서
            ordered_titles = ["수석", "차장", "과장", "대리", "사원", "기타"]
            # 추가 커스텀 직급이 있을 경우
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

            st.markdown("<hr style='margin: 15px 0; border-color: rgba(255,255,255,0.1);'>", unsafe_allow_html=True)
            st.markdown("##### ➕ 신규 직급 단가 추가 (선택)")
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
