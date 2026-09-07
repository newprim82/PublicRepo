import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from ...analytics.stats_service import StatsService
from ...services.reward_leave_service import RewardLeaveService
from ..common.dialogs import (
    show_worker_all_tasks_dialog,
    show_worker_category_tasks_dialog,
    show_kpi_urgent_dialog,
    show_weekly_detail_dialog
)
from ..common.ui_helpers import extract_week_sort_key, get_available_weeks_for_df, render_empty_week_notice

def render_worker_charts_interactive(display_summary: pd.DataFrame, df: pd.DataFrame, chart_orientation: str, selected_view: str):
    """팀원별 업무량 랭킹 & 작업 유형 차트 (화면 전체 새로고침 없는 독립 Fragment)"""
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



def render_weekly_matrix_section(mat_df: pd.DataFrame):
    """주차별 팀원 투입 시간 매트릭스 표 및 클릭 시 세부 팝업 (화면 전체 새로고침 없는 독립 Fragment)"""
    if not mat_df.empty and "week_label" in mat_df.columns:
        # 40시간 / 52시간 과중 업무 모니터링은 [교육] 구분 제외 기준으로 집계
        df_for_pivot = mat_df[~mat_df["log_type"].fillna("").astype(str).str.contains("교육")] if "log_type" in mat_df.columns else mat_df
        pivot_df = df_for_pivot.pivot_table(
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
                    msg_parts.append(f"🚨 <span style='color: #b91c1c; font-weight: 900;'>주 52시간 초과 위험 {danger_52_cnt}명 (빨간색)</span>")
                if caution_40_cnt > 0:
                    msg_parts.append(f"⚠️ <span style='color: #c2410c; font-weight: 900;'>주 40시간 초과 주의 {caution_40_cnt}명 (주황색)</span>")
                alert_text = f"{' / '.join(msg_parts)}이 감지되었습니다. (보상 완료: <b style='color:#15803d;'>{rewarded_cnt}명</b>) 숫자를 클릭하여 보상 휴가를 등록하시면 <b style='color:#15803d;'>녹색</b>으로 바뀝니다."
                st.markdown(f"""
                <div style="background-color: #fefce8; border: 1.5px solid #fef08a; border-left: 5.5px solid #eab308; border-radius: 8px; padding: 13px 18px; margin: 10px 0 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                    <div style="font-size: 13.5px; color: #713f12 !important; font-weight: 700; line-height: 1.6; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                        <span style="font-size: 16px;">⚠️</span>
                        <span style="color: #713f12 !important;">{alert_text}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            elif rewarded_cnt > 0:
                st.markdown(f"""
                <div style="background-color: #f0fdf4; border: 1.5px solid #bbf7d0; border-left: 5.5px solid #22c55e; border-radius: 8px; padding: 13px 18px; margin: 10px 0 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                    <div style="font-size: 13.5px; color: #14532d !important; font-weight: 700; line-height: 1.6; display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 16px;">🎉</span>
                        <span style="color: #14532d !important;">모든 초과 근무자(<b>{rewarded_cnt}명</b>)에게 <b>보상 휴가가 100% 정상 부여 완료</b>되었습니다! (녹색 전환)</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="background-color: #f0f9ff; border: 1.5px solid #bae6fd; border-left: 5.5px solid #0284c7; border-radius: 8px; padding: 13px 18px; margin: 10px 0 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                    <div style="font-size: 13.5px; color: #075985 !important; font-weight: 700; line-height: 1.6; display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 16px;">💡</span>
                        <span style="color: #075985 !important;">선택된 기간 동안 주 40시간을 초과한 과중 근무자가 없습니다.</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

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
                show_weekly_detail_dialog(target_w_name, mat_df, default_week_name=target_col_name)
            elif not current_click_token:
                st.session_state["_last_matrix_click_token"] = None



def render_worker_view(df: pd.DataFrame, selected_team: str, month_desc: str, df_raw: pd.DataFrame = None, team_mappings: dict = None):
    """👤 팀원별 업무량 분석 메인 뷰 (월간/주간 드릴다운 + 상단 차트/테이블 + 하단 주차별 매트릭스)"""
    
    # =========================================================================
    # 0. 📅 보고서 조회 주기 선택 (월간 전체 종합 vs 각 주차별 상세 드릴다운)
    # =========================================================================
    df_scope = df.copy()
    available_weeks = get_available_weeks_for_df(df_scope, month_desc=month_desc)

    period_options = ["📅 월간 전체 종합"] + [f"📌 {w}" for w in available_weeks]

    st.markdown("""
    <style>
        div.st-key-worker_view_period_selector [data-testid="stWidgetLabel"],
        div.st-key-worker_view_period_selector [data-testid="stWidgetLabel"] *,
        div.st-key-worker_view_period_selector label,
        div.st-key-worker_view_period_selector label * {
            color: #002d42 !important;
            font-size: 14.5px !important;
            font-weight: 800 !important;
        }
        div.st-key-worker_view_period_selector div[role="radiogroup"] {
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
        div.st-key-worker_view_period_selector div[role="radiogroup"] label {
            background: #f1f5f9 !important;
            border: 1.2px solid #cbd5e1 !important;
            border-radius: 6px !important;
            padding: 5px 12px !important;
            margin: 0 !important;
            cursor: pointer !important;
            transition: all 0.15s ease-in-out !important;
        }
        div.st-key-worker_view_period_selector div[role="radiogroup"] label:hover {
            background: #e2e8f0 !important;
            border-color: #0284c7 !important;
        }
        div.st-key-worker_view_period_selector div[role="radiogroup"] label p,
        div.st-key-worker_view_period_selector div[role="radiogroup"] label span {
            color: #002d42 !important;
            font-size: 13px !important;
            font-weight: 800 !important;
        }
        div.st-key-worker_view_period_selector div[role="radiogroup"] label[data-checked="true"],
        div.st-key-worker_view_period_selector div[role="radiogroup"] label:has(input:checked) {
            background: #005073 !important;
            border-color: #002d42 !important;
        }
        div.st-key-worker_view_period_selector div[role="radiogroup"] label[data-checked="true"] p,
        div.st-key-worker_view_period_selector div[role="radiogroup"] label:has(input:checked) p,
        div.st-key-worker_view_period_selector div[role="radiogroup"] label[data-checked="true"] span,
        div.st-key-worker_view_period_selector div[role="radiogroup"] label:has(input:checked) span {
            color: #ffffff !important;
            font-weight: 900 !important;
        }
    </style>
    <div style="font-size: 14.5px; font-weight: 800; color: #002d42 !important; margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
        <span>📅</span>
        <span style="color: #002d42 !important; font-weight: 800 !important;">보고서 조회 주기 선택 (월간 / 주간 드릴다운)</span>
    </div>
    """, unsafe_allow_html=True)

    if available_weeks:
        sel_period = st.radio(
            "보고서 조회 주기 선택 (월간 / 주간 드릴다운)",
            options=period_options,
            horizontal=True,
            key="worker_view_period_selector",
            label_visibility="collapsed"
        )
    else:
        sel_period = "📅 월간 전체 종합"

    # 팀명 안전 비교 헬퍼
    def is_same_team(t1, t2):
        return str(t1).replace(" ", "").strip() == str(t2).replace(" ", "").strip()

    # 선택된 주기에 따른 데이터 필터링 (df_active)
    if sel_period != "📅 월간 전체 종합":
        target_week = sel_period.replace("📌 ", "").strip()
        current_period_label = target_week
        if df_raw is not None and not df_raw.empty and "week_label" in df_raw.columns:
            df_active = df_raw[df_raw["week_label"] == target_week].copy()
        else:
            df_active = df_scope[df_scope["week_label"] == target_week].copy()

        if selected_team not in ["전체", "전체 팀"] and not df_active.empty:
            from ...services.team_service import UNASSIGNED_TEAM
            if team_mappings:
                df_active["worker_team"] = df_active["worker_name"].map(team_mappings).fillna(df_active.get("worker_team", "")).fillna(UNASSIGNED_TEAM)
            df_active = df_active[df_active["worker_team"].apply(lambda t: is_same_team(t, selected_team))]
    else:
        current_period_label = month_desc
        df_active = df_scope.copy()

    st.subheader(f"👤 {selected_team} - 팀원별 총 작업 시간 및 업무 집중도 ({current_period_label})")
    worker_summary = StatsService.get_worker_summary(df_active)
    
    if not worker_summary.empty:
        selected_view = "전체 보기"
        chart_orientation = "가로형 (이름 안 겹침 - 권장)"
        display_summary = worker_summary.copy()

        st.markdown("""<div style="background: linear-gradient(90deg, #f0f9ff 0%, #e0f2fe 100%); border: 1px solid #bae6fd; border-left: 4.5px solid #0284c7; border-radius: 6px; padding: 9px 15px; margin: 6px 0 16px 0; font-size: 13px; color: #0369a1; font-weight: 700; display: flex; align-items: center; gap: 8px;">
    <span>💡</span>
    <span><b>그래프의 막대(세그먼트)를 클릭</b>하시면, <b>[왼쪽 그래프: 개인 전체 작업 내역]</b>, <b>[오른쪽 그래프: 평일 주간/야간/주말별 상세 내역 및 카카오톡 원본]</b> 팝업이 바로 열립니다.</span>
    </div>""", unsafe_allow_html=True)
        
        render_worker_charts_interactive(display_summary, df_active, chart_orientation, current_period_label)

        st.markdown(f"##### 📊 팀원별 종합 통계 현황판 ({current_period_label})")
        disp_worker_summary = worker_summary.rename(columns={
            "worker_name": "담당자",
            "total_hours": "총 투입시간(h)",
            "total_tasks": "작업 건수",
            "weekday_day_tasks": "평일 주간 건수",
            "weekday_night_tasks": "평일 야간 건수",
            "weekend_tasks": "주말 작업 건수",
            "night_tasks": "야간 작업 건수",
            "avg_hours": "건당 평균시간(h)",
            "team": "소속팀",
            "title": "직급"
        })
        col_order = [
            "담당자", "소속팀", "직급",
            "총 투입시간(h)", "작업 건수",
            "평일 주간 건수", "평일 야간 건수", "주말 작업 건수", "야간 작업 건수",
            "건당 평균시간(h)"
        ]
        existing_cols = [c for c in col_order if c in disp_worker_summary.columns]
        other_cols = [c for c in disp_worker_summary.columns if c not in existing_cols]
        disp_worker_summary = disp_worker_summary[existing_cols + other_cols]

        st.dataframe(
            disp_worker_summary,
            use_container_width=True,
            hide_index=True
        )
    else:
        if sel_period != "📅 월간 전체 종합":
            render_empty_week_notice(target_week, selected_team)
        else:
            st.markdown(f"""
            <div style="background: #f8fafc; border: 1.5px solid #e2e8f0; border-left: 5.5px solid #64748b; border-radius: 8px; padding: 16px 20px; margin: 12px 0 20px 0; box-shadow: 0 2px 6px rgba(0,0,0,0.04);">
                <div style="font-size: 15px; font-weight: 800; color: #1e293b; margin-bottom: 6px; display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 18px;">📋</span>
                    <span style="color: #1e293b !important; font-weight: 800 !important;">선택하신 기간({current_period_label})은 <strong>카카오톡 원장 기록이 없습니다.</strong></span>
                </div>
                <div style="font-size: 13.5px; color: #334155 !important; line-height: 1.6;">
                    선택하신 <b>[{selected_team}]</b>의 해당 기간 동안 카카오톡 대화방에 등록된 시작/완료 작업 내역이 존재하지 않습니다.
                </div>
            </div>
            """, unsafe_allow_html=True)


    # ----------------------------------------------------
    # 📆 선택 월 주차(Week)별 팀원 투입 현황 & 과중 업무 모니터링 (사용자 요청 반영!)
    # ----------------------------------------------------
    st.markdown("---")
    st.markdown('<div id="weekly-monitor-section" style="scroll-margin-top: 60px;"></div>', unsafe_allow_html=True)
    st.markdown(f"##### 📆 {month_desc} - 주차(Week)별 팀원 투입 시간 현황 & 휴식 조율 모니터링")
    st.caption("선택된 월의 **각 주차별 투입 시간(h)**을 한눈에 비교하여, 한 주에 너무 많이 일한 팀원을 파악하고 다음 주 휴식을 조율할 수 있습니다. (💡 주 40h/52h 법정 기준에 따라 구분이 **[교육]**인 시간은 합산에서 제외됩니다.)")


    render_weekly_matrix_section(df)
