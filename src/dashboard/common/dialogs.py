import re
import time
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

import plotly.express as px
from .ui_helpers import inject_dialog_title_style, format_raw_chat_display, strip_tz
from ...services.email_report_service import EmailReportService
from ...services.email_sender import EmailSender
from ...services.team_service import TeamService
from ...services.reward_leave_service import RewardLeaveService
from ...analytics.stats_service import StatsService


def render_chat_messages_expander(target_df: pd.DataFrame, max_display: int = 20, title_prefix: str = "전체 작업"):
    """모달 내 카카오톡 원본 메시지를 상위 N건으로 제한 렌더링하여 DOM 폭발 및 브라우저 프리징 방지"""
    total_cnt = len(target_df)
    if total_cnt == 0:
        return
    display_cnt = min(total_cnt, max_display)
    title = f"💬 {title_prefix} 카카오톡 원본 메시지 ({total_cnt}건 중 최근 {display_cnt}건)"
    with st.expander(title, expanded=False):
        for i, (_, r) in enumerate(target_df.head(max_display).iterrows()):
            start_str = r['start_time'].strftime('%Y-%m-%d %H:%M') if pd.notna(r.get('start_time')) else ''
            w_name = r.get('worker_name', '')
            c_name = r.get('client_name', '')
            t_desc = r.get('task_description', '')
            est_h = r.get('estimated_hours', 0)
            act_h = r.get('actual_hours', 0)
            st.markdown(f"**[작업 #{i+1}] {start_str} | {w_name} - {c_name} ({t_desc}) [예정:{est_h}h ➔ 소요:{act_h}h]**")
            st.code(format_raw_chat_display(r), language="text")
            st.divider()
        if total_cnt > max_display:
            st.caption(f"💡 표에서 행을 클릭하시면 개별 원본 대화를 확인하실 수 있습니다. (성능 최적화를 위해 최근 {max_display}건만 표시됩니다)")

@st.dialog("🔍 세부 작업 내역 및 카카오톡 원본 분석", width="large")
def show_weekly_detail_dialog(target_worker: str, df_data: pd.DataFrame, default_week_name: str = None):
    inject_dialog_title_style()
    worker_df = df_data[df_data["worker_name"] == target_worker]
    if "status" in worker_df.columns:
        worker_df = worker_df[worker_df["status"].isin(["COMPLETED", "PENDING"])]
    if worker_df.empty:
        st.warning(f"[{target_worker}] 님의 작업 데이터가 없습니다.")
        return

    # 주차 목록 (시간 많은 순 정렬 - 40h/52h 초과 판단은 교육 및 휴가 제외 실근로시간 기준)
    worker_df_work = worker_df[~worker_df["log_type"].fillna("").astype(str).str.contains("교육|휴가")] if "log_type" in worker_df.columns else worker_df
    wk_work_hours = worker_df_work.groupby("week_label")["actual_hours"].sum().to_dict()

    wk_agg = worker_df.groupby("week_label")["actual_hours"].agg(["sum", "count"]).reset_index()
    wk_agg = wk_agg.sort_values(by="sum", ascending=False)

    wk_options = []
    wk_map = {}
    default_pick_idx = 0

    for idx, (_, r) in enumerate(wk_agg.iterrows()):
        lbl = r["week_label"]
        s = round(r["sum"], 1)
        c = int(r["count"])
        work_s = round(wk_work_hours.get(lbl, 0.0), 1)
        alert_icon = " 🚨 (주 52h 초과)" if work_s >= 52.0 else (" ⚠️ (주 40h 초과)" if work_s >= 40.0 else "")
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

        # 교육 및 휴가 제외 근로시간 산정 (주 40h / 52h 법정 기준 산정용)
        detail_work = detail[~detail["log_type"].fillna("").astype(str).str.contains("교육|휴가")] if "log_type" in detail.columns else detail
        tot_work_h = round(detail_work["actual_hours"].sum(), 1)
        edu_h = round(tot_h - tot_work_h, 1)

        # 지표 카드 (주 52시간 기준 산정 - 교육 제외 실근로시간 기준)
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            metric_label = "해당 주차 실 근로시간 (교육제외)" if edu_h > 0 else "해당 주차 총 투입 시간"
            delta_msg = f"{round(tot_work_h - 52.0, 1)}h 초과!" if tot_work_h >= 52.0 else "주 52h 이내 정상"
            st.metric(
                metric_label,
                f"{tot_work_h}시간",
                delta=delta_msg,
                delta_color="inverse" if tot_work_h >= 52.0 else "normal",
                help=f"총 투입: {tot_h}h (교육 {edu_h}h 제외됨)" if edu_h > 0 else "교육 제외 실근로시간 기준"
            )
            if edu_h > 0:
                st.caption(f"💡 총 {tot_h}h 중 교육 {edu_h}h 제외됨")
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
            if tot_work_h >= 52.0:
                danger_html = (
                    '<div class="overwork-danger-box" style="background-color: #fee2e2 !important; background: #fee2e2 !important; border: 1.5px solid #f87171 !important; border-left: 6px solid #ef4444 !important; border-radius: 8px !important; padding: 13px 18px !important; margin-bottom: 14px !important; display: block !important;">'
                    '<div style="color: #7f1d1d !important; font-weight: 800 !important; font-size: 13.5px !important; line-height: 1.6 !important;">'
                    '<span style="font-size: 16px !important; margin-right: 4px;">🚨</span>'
                    f'<span style="color: #000000 !important; font-weight: 900 !important;">주 52시간 초과 근무 <span style="color: #991b1b !important; font-weight: 900;">{round(tot_work_h - 52.0, 1)}시간 발생</span> (교육 제외 {tot_work_h}h, 미보상 상태).</span>'
                    '<span style="color: #1e293b !important; font-weight: 700 !important; margin-left: 4px;">아래에서 보상 휴가를 등록하시면 표의 색상이 <b style="color: #15803d !important;">초록색</b>으로 전환됩니다.</span>'
                    '</div></div>'
                )
                st.markdown(danger_html, unsafe_allow_html=True)
            elif tot_work_h >= 40.0:
                warning_html = (
                    '<div class="overwork-warning-box" style="background-color: #fef08a !important; background: #fef08a !important; border: 1.5px solid #facc15 !important; border-left: 6px solid #ca8a04 !important; border-radius: 8px !important; padding: 13px 18px !important; margin-bottom: 14px !important; display: block !important;">'
                    '<div style="color: #451a03 !important; font-weight: 800 !important; font-size: 13.5px !important; line-height: 1.6 !important;">'
                    '<span style="font-size: 16px !important; margin-right: 4px;">⚠️</span>'
                    f'<span style="color: #000000 !important; font-weight: 900 !important;">주 40시간 초과(교육 제외 {tot_work_h}시간) 주차입니다.</span>'
                    '<span style="color: #1e293b !important; font-weight: 700 !important; margin-left: 6px;">필요 시 보상 휴가를 등록하시면 표에 반영됩니다.</span>'
                    '</div></div>'
                )
                st.markdown(warning_html, unsafe_allow_html=True)
            else:
                st.info("💡 해당 주차는 주 52시간 이내 정상이지만, 필요 시 특별 보상 휴가를 등록할 수 있습니다.")

            with st.form(f"form_reward_leave_{target_worker}_{target_wk}"):
                col_hrs, col_note = st.columns([1, 2])
                with col_hrs:
                    default_leave_hrs = 8.0 if tot_work_h >= 52.0 else 4.0
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

        # 카카오톡 원본 메시지 아코디언 (상위 20건 제한 경량화)
        render_chat_messages_expander(detail, max_display=20, title_prefix="카카오톡 시작/완료")



# ----------------------------------------------------
# 🌟 5대 핵심 KPI 카드별 세부 내역 팝업 모달 (@st.dialog)
# ----------------------------------------------------
@st.dialog("⏱️ 총 지원 시간 세부 작업 내역", width="large")
def show_kpi_total_hours_dialog(df_data: pd.DataFrame):
    inject_dialog_title_style()
    if df_data.empty:
        st.info("데이터가 없습니다.")
        return
    if "status" in df_data.columns:
        df_data = df_data[df_data["status"].isin(["COMPLETED", "PENDING"])]
    if df_data.empty:
        st.info("실제 완료 및 진행 중인 작업 데이터가 없습니다.")
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

    render_chat_messages_expander(sorted_df, max_display=20, title_prefix="전체 작업")


@st.dialog("📋 총 작업 건수 세부 내역 (완료 / 진행 중)", width="large")
def show_kpi_total_tasks_dialog(df_data: pd.DataFrame):
    inject_dialog_title_style()
    if df_data.empty:
        st.info("데이터가 없습니다.")
        return
    if "status" in df_data.columns:
        df_data = df_data[df_data["status"].isin(["COMPLETED", "PENDING"])]
    if df_data.empty:
        st.info("실제 완료 및 진행 중인 작업 데이터가 없습니다.")
        return
    comp_df = df_data[df_data["status"] == "COMPLETED"].sort_values(by="start_time", ascending=False).reset_index(drop=True)
    pend_df = df_data[df_data["status"] == "PENDING"].sort_values(by="start_time", ascending=False).reset_index(drop=True)
    
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
            disp_pend["end_time"] = None  # 🌟 진행 중인 작업은 미완료 상태이므로 완료 보고시각은 None 보장
            
            # 🛡️ PENDING 다일 작업의 일일 9.0h 예정시간 및 (1/N일차) 표기 안전 보장 (27h 표출 원천 방지)
            for p_i, p_r in disp_pend.iterrows():
                raw_s = str(p_r.get("raw_start_message") or "")
                m_d = re.search(r'(\d+(?:\.\d+)?)\s*(?:days?|d(?![a-zA-Z])|D|일)', raw_s, re.IGNORECASE)
                if m_d and float(m_d.group(1)) >= 1.5:
                    tot_d = int(float(m_d.group(1)))
                    disp_pend.at[p_i, "estimated_hours"] = 9.0
                    cur_desc = str(p_r.get("task_description") or "").strip()
                    if not re.search(r'\(\d+/\d+일차\)', cur_desc):
                        disp_pend.at[p_i, "task_description"] = f"{cur_desc} (1/{tot_d}일차)"
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
    if "status" in df_data.columns:
        df_data = df_data[df_data["status"].isin(["COMPLETED", "PENDING"])]
    if df_data.empty:
        st.info("실제 완료 및 진행 중인 작업 데이터가 없습니다.")
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
    if "status" in df_data.columns:
        df_data = df_data[df_data["status"].isin(["COMPLETED", "PENDING"])]
    if df_data.empty:
        st.info("실제 완료 및 진행 중인 작업 데이터가 없습니다.")
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
    if "status" in df_data.columns:
        df_data = df_data[df_data["status"].isin(["COMPLETED", "PENDING"])]
    if df_data.empty:
        st.info("실제 완료 및 진행 중인 작업 데이터가 없습니다.")
        return
    # 예정 시간이 0h 초과인 작업 중에서 실제 소요 시간이 예정 시간을 초과한 건만 필터링 (0h 미입력 건은 제외)
    overdue_df = df_data[(df_data["actual_hours"] > df_data["estimated_hours"]) & (df_data["estimated_hours"] > 0)].copy()
    if not overdue_df.empty:
        overdue_df["diff_hours"] = (overdue_df["actual_hours"] - overdue_df["estimated_hours"]).round(1)
        overdue_df = overdue_df.sort_values(by="diff_hours", ascending=False).reset_index(drop=True)
        
    valid_est_df = df_data[df_data["estimated_hours"] > 0]
    denom = len(valid_est_df) if not valid_est_df.empty else len(df_data)
    overdue_rate = round(len(overdue_df) / max(denom, 1) * 100, 1)
    st.markdown(f"### ⚠️ 예정 시간 초과 작업: 총 **{len(overdue_df)}건** (초과율 {overdue_rate}%)")
    
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

        render_chat_messages_expander(overdue_df, max_display=20, title_prefix="초과 작업")



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

    render_chat_messages_expander(w_df, max_display=20, title_prefix="전체 작업")


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

    render_chat_messages_expander(cat_df, max_display=20, title_prefix=f"전체 [{cat_name}]")




@st.dialog("🏢 팀별 세부 작업 원장 및 카카오톡 원본", width="large")
def show_team_work_logs_dialog(team_name: str, team_logs_df: pd.DataFrame):
    """팀 클릭 시 열리는 상세 작업 원장 모달 팝업"""
    inject_dialog_title_style()
    if team_logs_df.empty:
        st.info(f"[{team_name}]의 작업 데이터가 없습니다.")
        return

    tot_h = round(team_logs_df["actual_hours"].sum(), 1)
    tot_tasks = len(team_logs_df)
    tot_w = team_logs_df["worker_name"].nunique()
    tot_c = team_logs_df["client_name"].nunique()
    comp_cnt = int((team_logs_df["status"] == "COMPLETED").sum())
    pend_cnt = int((team_logs_df["status"] == "PENDING").sum())
    night_cnt = int((team_logs_df["is_night_work"] == True).sum()) if "is_night_work" in team_logs_df.columns else 0

    st.markdown(f"### 🏢 **{team_name}** 세부 작업 원장")
    # 상단 요약 배너
    st.markdown(
        f"""<div style="display: flex; gap: 10px; margin-bottom: 16px; background: #ffffff; border: 1px solid #e1e4e8; border-radius: 8px; padding: 10px 14px; flex-wrap: wrap; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
<span style="color: #005073; font-weight: 700;">⏱️ 총 공수: <b>{tot_h}h</b> ({tot_tasks}건)</span>
<span style="color: #cbd5e1;">|</span>
<span style="color: #4f46e5; font-weight: 700;">👥 투입 인원: <b>{tot_w}명</b></span>
<span style="color: #cbd5e1;">|</span>
<span style="color: #d97706; font-weight: 700;">🏢 고객사: <b>{tot_c}개사</b></span>
<span style="color: #cbd5e1;">|</span>
<span style="color: #dc2626; font-weight: 700;">🌙 야간작업: <b>{night_cnt}건</b></span>
<span style="color: #cbd5e1;">|</span>
<span style="color: #0f5132; font-weight: 700;">✅ 완료 {comp_cnt}건 / ⏳ 진행 {pend_cnt}건</span>
</div>""",
        unsafe_allow_html=True
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        top_clients = team_logs_df.groupby("client_name")["actual_hours"].sum().sort_values(ascending=False).head(5).reset_index()
        if not top_clients.empty:
            fig1 = px.bar(top_clients, x="actual_hours", y="client_name", orientation="h", text="actual_hours", title=f"🏢 {team_name} 상위 고객사 투입 시간(h)")
            fig1.update_layout(height=200, yaxis={'categoryorder': 'total ascending'}, margin=dict(l=20, r=20, t=35, b=20))
            st.plotly_chart(fig1, use_container_width=True)
    with c2:
        top_workers = team_logs_df.groupby("worker_name")["actual_hours"].sum().sort_values(ascending=False).head(5).reset_index()
        if not top_workers.empty:
            fig2 = px.bar(top_workers, x="actual_hours", y="worker_name", orientation="h", text="actual_hours", title=f"👤 {team_name} 상위 팀원 투입 시간(h)")
            fig2.update_layout(height=200, yaxis={'categoryorder': 'total ascending'}, margin=dict(l=20, r=20, t=35, b=20))
            st.plotly_chart(fig2, use_container_width=True)

    sorted_df = team_logs_df.sort_values(by="start_time", ascending=False).reset_index(drop=True)
    disp_sorted_df = strip_tz(sorted_df.copy())
    if "end_time" not in disp_sorted_df.columns:
        disp_sorted_df["end_time"] = None
    if "status" in disp_sorted_df.columns:
        disp_sorted_df["status"] = disp_sorted_df["status"].map({"PENDING": "진행 중", "COMPLETED": "완료"}).fillna(disp_sorted_df["status"])

    st.markdown("#### 📋 팀 전체 지원 작업 상세 원장")
    st.caption("💡 표에서 특정 행을 클릭하시면, 해당 작업의 **카카오톡 시작/완료 원본 메시지**를 바로 아래에서 확인하실 수 있습니다.")

    table_cols = ["start_time", "end_time", "worker_name", "worker_team", "client_name", "task_description", "estimated_hours", "actual_hours", "status"]
    avail_cols = [col for col in table_cols if col in disp_sorted_df.columns]

    sel_tbl = st.dataframe(
        disp_sorted_df[avail_cols].rename(columns={
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
        selection_mode="single-row",
        key=f"tbl_team_popup_{abs(hash(str(team_name))) % 100000}"
    )

    if sel_tbl and hasattr(sel_tbl, "selection") and sel_tbl.selection.rows:
        sel_idx = sel_tbl.selection.rows[0]
        sel_row = sorted_df.iloc[sel_idx]
        st.markdown(f"##### 💬 [{sel_row['worker_name']} | {sel_row['client_name']}] 카카오톡 대화 원본")
        st.code(format_raw_chat_display(sel_row), language="text")

    render_chat_messages_expander(sorted_df, max_display=20, title_prefix="전체 작업")


@st.dialog("📆 주차별 세부 지원 내역 및 카카오톡 원본", width="large")
def show_week_summary_dialog(week_title: str, week_df: pd.DataFrame):
    """주차별 막대 클릭 시 열리는 상세 작업 내역 모달 팝업"""
    inject_dialog_title_style()
    if week_df.empty:
        st.info("해당 주차의 작업 데이터가 없습니다.")
        return

    tot_h = round(week_df["actual_hours"].sum(), 1)
    tot_tasks = len(week_df)
    tot_w = week_df["worker_name"].nunique()
    tot_c = week_df["client_name"].nunique()
    comp_cnt = int((week_df["status"] == "COMPLETED").sum())
    pend_cnt = int((week_df["status"] == "PENDING").sum())

    st.markdown(f"### 📆 **{week_title}** 세부 지원 내역")
    # 상단 요약 배너
    st.markdown(
        f"""<div style="display: flex; gap: 10px; margin-bottom: 16px; background: #ffffff; border: 1px solid #e1e4e8; border-radius: 8px; padding: 10px 14px; flex-wrap: wrap; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
<span style="color: #005073; font-weight: 700;">⏱️ 총 공수: <b>{tot_h}h</b> ({tot_tasks}건)</span>
<span style="color: #cbd5e1;">|</span>
<span style="color: #4f46e5; font-weight: 700;">👥 투입 인원: <b>{tot_w}명</b></span>
<span style="color: #cbd5e1;">|</span>
<span style="color: #d97706; font-weight: 700;">🏢 고객사: <b>{tot_c}개사</b></span>
<span style="color: #cbd5e1;">|</span>
<span style="color: #0f5132; font-weight: 700;">✅ 완료 {comp_cnt}건 / ⏳ 진행 {pend_cnt}건</span>
</div>""",
        unsafe_allow_html=True
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        top_clients = week_df.groupby("client_name")["actual_hours"].sum().sort_values(ascending=False).head(5).reset_index()
        if not top_clients.empty:
            fig1 = px.bar(top_clients, x="actual_hours", y="client_name", orientation="h", text="actual_hours", title="🏢 상위 고객사 투입 시간(h)")
            fig1.update_layout(height=200, yaxis={'categoryorder': 'total ascending'}, margin=dict(l=20, r=20, t=35, b=20))
            st.plotly_chart(fig1, use_container_width=True)
    with c2:
        top_workers = week_df.groupby("worker_name")["actual_hours"].sum().sort_values(ascending=False).head(5).reset_index()
        if not top_workers.empty:
            fig2 = px.bar(top_workers, x="actual_hours", y="worker_name", orientation="h", text="actual_hours", title="👤 상위 담당자 투입 시간(h)")
            fig2.update_layout(height=200, yaxis={'categoryorder': 'total ascending'}, margin=dict(l=20, r=20, t=35, b=20))
            st.plotly_chart(fig2, use_container_width=True)

    sorted_df = week_df.sort_values(by="start_time", ascending=False).reset_index(drop=True)
    disp_sorted_df = strip_tz(sorted_df.copy())
    if "end_time" not in disp_sorted_df.columns:
        disp_sorted_df["end_time"] = None
    if "status" in disp_sorted_df.columns:
        disp_sorted_df["status"] = disp_sorted_df["status"].map({"PENDING": "진행 중", "COMPLETED": "완료"}).fillna(disp_sorted_df["status"])

    st.markdown("#### 📋 해당 주차 전체 작업 상세 목록")
    st.caption("💡 표에서 특정 행을 클릭하시면, 해당 작업의 **카카오톡 시작/완료 원본 메시지**를 바로 아래에서 확인하실 수 있습니다.")

    table_cols = ["start_time", "end_time", "worker_name", "worker_team", "client_name", "task_description", "estimated_hours", "actual_hours", "status"]
    avail_cols = [col for col in table_cols if col in disp_sorted_df.columns]

    sel_tbl = st.dataframe(
        disp_sorted_df[avail_cols].rename(columns={
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
        selection_mode="single-row",
        key=f"tbl_week_popup_{abs(hash(week_title)) % 100000}"
    )

    if sel_tbl and hasattr(sel_tbl, "selection") and sel_tbl.selection.rows:
        sel_idx = sel_tbl.selection.rows[0]
        sel_row = sorted_df.iloc[sel_idx]
        st.markdown(f"##### 💬 [{sel_row['worker_name']} | {sel_row['client_name']}] 카카오톡 대화 원본")
        st.code(format_raw_chat_display(sel_row), language="text")

    render_chat_messages_expander(sorted_df, max_display=20, title_prefix="전체 작업")


@st.dialog("📅 일자별 세부 작업 내역", width="large")
def show_calendar_day_dialog(date_title: str, day_df: pd.DataFrame):
    """일자 클릭 시 열리는 상세 작업 내역 원장 모달 팝업"""
    inject_dialog_title_style()
    if day_df.empty:
        st.info("해당 일자에 등록된 작업 내역이 없습니다.")
        return

    tot_h = round(day_df["actual_hours"].sum(), 1)
    tot_tasks = len(day_df)
    tot_w = day_df["worker_name"].nunique()
    tot_c = day_df["client_name"].nunique()
    comp_cnt = int((day_df["status"] == "COMPLETED").sum())
    pend_cnt = int((day_df["status"] == "PENDING").sum())

    st.markdown(f"### 📅 **{date_title}** 세부 작업 원장")
    # 상단 요약 배너
    st.markdown(
        f"""<div style="display: flex; gap: 10px; margin-bottom: 16px; background: #ffffff; border: 1px solid #e1e4e8; border-radius: 8px; padding: 10px 14px; flex-wrap: wrap; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
<span style="color: #005073; font-weight: 700;">⏱️ 총 공수: <b>{tot_h}h</b> ({tot_tasks}건)</span>
<span style="color: #cbd5e1;">|</span>
<span style="color: #4f46e5; font-weight: 700;">👥 투입 인원: <b>{tot_w}명</b></span>
<span style="color: #cbd5e1;">|</span>
<span style="color: #d97706; font-weight: 700;">🏢 고객사: <b>{tot_c}개사</b></span>
<span style="color: #cbd5e1;">|</span>
<span style="color: #0f5132; font-weight: 700;">✅ 완료 {comp_cnt}건 / ⏳ 진행 {pend_cnt}건</span>
</div>""",
        unsafe_allow_html=True
    )

    sorted_df = day_df.sort_values(by="start_time", ascending=True).reset_index(drop=True)
    disp_sorted_df = strip_tz(sorted_df.copy())
    if "end_time" not in disp_sorted_df.columns:
        disp_sorted_df["end_time"] = None
    if "status" in disp_sorted_df.columns:
        disp_sorted_df["status"] = disp_sorted_df["status"].map({"PENDING": "진행 중", "COMPLETED": "완료"}).fillna(disp_sorted_df["status"])

    st.markdown("#### 📋 전체 지원 작업 상세 원장")
    st.caption("💡 표에서 특정 행을 클릭하시면, 해당 작업의 **카카오톡 시작/완료 원본 메시지**를 바로 아래에서 확인하실 수 있습니다.")

    table_cols = ["start_time", "end_time", "worker_name", "worker_team", "client_name", "task_description", "estimated_hours", "actual_hours", "status"]
    avail_cols = [col for col in table_cols if col in disp_sorted_df.columns]

    sel_tbl = st.dataframe(
        disp_sorted_df[avail_cols].rename(columns={
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
        selection_mode="single-row",
        key=f"tbl_day_popup_{abs(hash(str(date_title))) % 100000}"
    )

    if sel_tbl and hasattr(sel_tbl, "selection") and sel_tbl.selection.rows:
        sel_idx = sel_tbl.selection.rows[0]
        sel_row = sorted_df.iloc[sel_idx]
        st.markdown(f"##### 💬 [{sel_row['worker_name']} | {sel_row['client_name']}] 카카오톡 대화 원본")
        st.code(format_raw_chat_display(sel_row), language="text")

    render_chat_messages_expander(sorted_df, max_display=20, title_prefix="전체 작업")




@st.dialog("📧 업무 실적 Summary 메일 발송", width="medium")
def show_email_report_dialog(selected_team: str):
    """업무 실적 Summary 이메일 발송 전용 팝업 모달 (화면 데이터 100% 동기화)"""
    ctx = st.session_state.get("exec_summary_context", {})
    period_label = ctx.get("current_period_label", f"{selected_team} - 실적 Summary")
    df_active = ctx.get("df_active", None)
    prev_df = ctx.get("prev_df", None)
    ai_briefing = ctx.get("ai_briefing", None)
    available_weeks = ctx.get("available_weeks", None)
    df_scope = ctx.get("df_scope", None)
    team_mappings = ctx.get("team_mappings", None)

    st.markdown(
        f"""
        <div style="background: rgba(2, 132, 199, 0.15); border: 1px solid rgba(56, 189, 248, 0.3); border-left: 4px solid #38bdf8; padding: 12px 16px; border-radius: 6px; font-size: 13px; color: #FFFFFF !important; line-height: 1.6; margin-bottom: 15px;">
            📌 현재 화면에서 조회 중인 <b style="color: #38bdf8;">[{period_label}]</b>의 서머리 페이지 모든 내용(핵심 지표, AI 브리핑, 주차별 비교표, 법정근로시간 거버넌스, 고객사 파레토 분석, 전체 팀원 현황, 부서별 집계표)과 <b style="color: #38bdf8;">상세 실적 다중 시트 엑셀 파일</b>을 지정한 메일 주소로 즉시 전송합니다.
        </div>
        """,
        unsafe_allow_html=True
    )
    
    mail_rcpt = st.text_input(
        "수신자 이메일 (쉼표로 복수 지정 가능)",
        value="ymmoon@sangsanginworld.co.kr",
        key="dialog_recipient_email"
    )
    st.markdown("<div style='font-size: 12px; color: #cbd5e1; margin-top: -6px; margin-bottom: 12px;'>발신 계정: <b style='color: #38bdf8;'>newprim82@gmail.com</b> (Gmail SMTP 연동 완료)</div>", unsafe_allow_html=True)
    st.write("")
    
    if st.button("🚀 보고서 즉시 발송", type="primary", use_container_width=True, key="btn_confirm_send_email"):
        with st.spinner("🤖 Gemini AI 심층 브리핑 생성 및 이메일 전송 중..."):
            success, send_msg = EmailSender.send_weekly_report(
                recipient_emails=mail_rcpt,
                sender_email="newprim82@gmail.com",
                sender_password="dlugbvfuhgdozkgr",
                selected_team=selected_team,
                df_active_override=df_active,
                prev_df_override=prev_df,
                ai_briefing_override=ai_briefing,
                current_period_label_override=period_label,
                available_weeks_override=available_weeks,
                df_scope_override=df_scope,
                team_mappings_override=team_mappings,
                dispatch_type="MANUAL_IMMEDIATE"
            )
            if success:
                st.success(send_msg)
            else:
                st.error(send_msg)

    # ==========================================
    # 📋 최근 메일 발송 이력 (최근 5회)
    # ==========================================
    st.markdown("<div style='margin-top: 18px; margin-bottom: 12px; border-top: 1px solid rgba(255, 255, 255, 0.12);'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 9px;">
            <div style="font-size: 13.5px; font-weight: 800; color: #38bdf8; display: flex; align-items: center; gap: 6px;">
                <span>📋</span><span>최근 메일 발송 이력 (최근 5회)</span>
            </div>
            <span style="font-size: 11px; color: #94a3b8;">DB 자동 기록 중</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    try:
        from src.services.email_dispatch_service import EmailDispatchService
        recent_logs = EmailDispatchService.get_recent_dispatches(limit=5)
    except Exception as e:
        recent_logs = []

    if not recent_logs:
        st.markdown(
            """
            <div style="background: rgba(15, 23, 42, 0.4); border: 1px dashed rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 14px; text-align: center; color: #94a3b8; font-size: 12px;">
                아직 발송된 메일 이력이 없습니다.
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        type_badge_map = {
            "MANUAL_IMMEDIATE": ('<span style="background:#0284c7; color:#ffffff; padding:2px 7px; border-radius:4px; font-size:10.5px; font-weight:800;">🚀 수동 즉시</span>', "수동 즉시 발송"),
            "AUTO_WEEKLY": ('<span style="background:#16a34a; color:#ffffff; padding:2px 7px; border-radius:4px; font-size:10.5px; font-weight:800;">⏳ 주간 자동</span>', "주간 자동 발송"),
            "AUTO_MONTHLY": ('<span style="background:#7c3aed; color:#ffffff; padding:2px 7px; border-radius:4px; font-size:10.5px; font-weight:800;">📅 월간 자동</span>', "월간 자동 발송")
        }

        for item in recent_logs:
            d_type = item.get("dispatch_type", "MANUAL_IMMEDIATE")
            badge_html, _ = type_badge_map.get(
                d_type,
                ('<span style="background:#64748b; color:#ffffff; padding:2px 7px; border-radius:4px; font-size:10.5px; font-weight:800;">메일 발송</span>', "메일 발송")
            )
            status = item.get("status", "SUCCESS")
            status_html = '<span style="color:#4ade80; font-weight:800; font-size:11.5px;">✅ 성공</span>' if status == "SUCCESS" else '<span style="color:#f87171; font-weight:800; font-size:11.5px;" title="' + str(item.get("error_message", "")) + '">❌ 실패</span>'
            dt_str = str(item.get("created_at", "")).replace("T", " ")
            short_dt = dt_str[5:16] if len(dt_str) >= 16 else dt_str

            p_label = item.get("period_label", "")
            rcpts = item.get("recipient_emails", "")
            rcpts_display = (rcpts[:30] + "...") if len(rcpts) > 33 else rcpts

            card_html = f"""
            <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 8px 12px; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center; gap: 10px; font-size: 12px;">
                <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                    {badge_html}
                    <span style="color: #cbd5e1; font-weight: 600;">{p_label}</span>
                    <span style="color: #64748b;">|</span>
                    <span style="color: #94a3b8; font-size: 11px;">수신: {rcpts_display}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 10px; white-space: nowrap;">
                    <span style="color: #94a3b8; font-size: 11px;">{short_dt}</span>
                    {status_html}
                </div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)


@st.dialog("🧹 24시간 초과 미마감(진행 중) 작업 정리 도구", width="large")
def show_stale_pending_tasks_dialog(df_data: pd.DataFrame):
    inject_dialog_title_style()
    now = datetime.now()
    
    if df_data.empty or "status" not in df_data.columns:
        st.info("작업 데이터가 없습니다.")
        return
        
    pend_df = df_data[df_data["status"] == "PENDING"].copy()
    if pend_df.empty:
        st.success("🎉 현재 진행 중인 미완료 작업이 없습니다.")
        return
        
    now_naive = now.replace(tzinfo=None) if hasattr(now, "tzinfo") and now.tzinfo else now
    def _to_naive_dt(val):
        if pd.isna(val) or not val:
            return pd.NaT
        if isinstance(val, str):
            clean_str = val.replace("T", " ").replace("Z", "")
            if "+" in clean_str:
                clean_str = clean_str.split("+")[0]
            return pd.to_datetime(clean_str.strip(), errors="coerce")
        if hasattr(val, "tz_localize") and getattr(val, "tz", None) is not None:
            return val.tz_localize(None)
        if hasattr(val, "replace") and getattr(val, "tzinfo", None) is not None:
            return val.replace(tzinfo=None)
        return pd.to_datetime(val, errors="coerce")

    pend_df["_st_dt"] = pd.Series([_to_naive_dt(v) for v in pend_df["start_time"]], index=pend_df.index)
    stale_mask = (now_naive - pend_df["_st_dt"]) >= timedelta(hours=24)
    stale_df = pend_df[stale_mask].sort_values(by="_st_dt", ascending=True).reset_index(drop=True)
    
    if stale_df.empty:
        st.success("🎉 24시간을 초과하여 방치된 미마감 작업이 없습니다. 모든 진행 작업이 정상 윈도우 내에 있습니다.")
        return

    stale_df["elapsed_hours"] = ((now_naive - stale_df["_st_dt"]).dt.total_seconds() / 3600.0).round(1)
    
    st.markdown(f"### ⚠️ 24시간 이상 미마감 작업: 총 **{len(stale_df)}건**")
    st.caption("카카오톡 완료 보고를 누락하여 하루 이상 '진행 중'으로 남아있는 작업입니다. 예정시간 기준으로 일괄 완료 처리하거나, 개별 완료시간을 지정하여 마감할 수 있습니다.")

    c_btn1, c_btn2 = st.columns([1.5, 2.5])
    with c_btn1:
        if st.button("⚡ 전체 예정시간 기준 일괄 완료", type="primary", use_container_width=True, help="모든 미마감 작업을 각 작업의 예정시간(미지정시 1시간)으로 즉시 완료 마감합니다."):
            hashes = stale_df["msg_hash"].dropna().tolist()
            from src.database.supabase_client import db_manager
            updated = db_manager.resolve_stale_pending_tasks(hashes)
            st.success(f"총 {updated}건의 미마감 작업이 정상적으로 완료 마감되었습니다!")
            from src.dashboard.app import clear_all_web_caches
            clear_all_web_caches()
            st.rerun()

    st.markdown("---")
    
    disp_df = stale_df.copy()
    disp_df["start_str"] = disp_df["_st_dt"].dt.strftime("%Y-%m-%d %H:%M")
    
    sel = st.dataframe(
        disp_df[[
            "start_str", "worker_name", "worker_team", "client_name", "task_description",
            "estimated_hours", "elapsed_hours"
        ]].rename(columns={
            "start_str": "시작일시",
            "worker_name": "담당자",
            "worker_team": "소속팀",
            "client_name": "고객사",
            "task_description": "작업내용",
            "estimated_hours": "예정(h)",
            "elapsed_hours": "경과시간(h)"
        }),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="stale_tasks_table"
    )
    
    if sel and hasattr(sel, "selection") and sel.selection.rows:
        sel_row = stale_df.iloc[sel.selection.rows[0]]
        st.markdown(f"#### ⏱️ [{sel_row['worker_name']} | {sel_row['client_name']}] 개별 마감 처리")
        
        c1, c2, c3 = st.columns([1.5, 1.5, 1])
        with c1:
            est_default = float(sel_row.get("estimated_hours") or 1.0)
            custom_h = st.number_input("소요 시간(시간)", min_value=0.5, max_value=24.0, value=max(0.5, est_default), step=0.5, key="num_custom_h")
        with c2:
            st.write("")
            st.write("")
            if st.button("✅ 이 작업만 완료 마감", use_container_width=True):
                from src.database.supabase_client import db_manager
                custom_m = int(custom_h * 60)
                m_hash = sel_row.get("msg_hash")
                if m_hash:
                    db_manager.resolve_stale_pending_tasks([m_hash], custom_minutes_map={m_hash: custom_m})
                    st.success(f"{sel_row['worker_name']} 님의 작업이 {custom_h}시간 완료 마감되었습니다!")
                    from src.dashboard.app import clear_all_web_caches
                    clear_all_web_caches()
                    st.rerun()



