import html
import io
import re
from datetime import datetime, timezone, timedelta
import pandas as pd
import streamlit as st
from ...services.team_service import TeamService, UNASSIGNED_TEAM
from ...services.reward_leave_service import RewardLeaveService
from ...analytics.stats_service import StatsService
from ...database.supabase_client import db_manager
from ..common.dialogs import (
    show_kpi_total_hours_dialog,
    show_kpi_total_tasks_dialog,
    show_kpi_workers_dialog,
    show_kpi_urgent_dialog,
    show_kpi_overdue_dialog,
    show_weekly_detail_dialog
)
from ..common.ui_helpers import (
    strip_tz,
    get_job_title_badge,
    get_job_title_color,
    get_job_title_rank,
    get_team_theme,
    get_live_task_card_html,
    get_leave_card_html,
    is_same_team,
    format_raw_chat_display,
    get_current_kst_time,
    LIVE_PROGRESS_ANIMATION_AND_TIMER
)
from .outlook_calendar_widget import render_outlook_calendar_widget
from ...services.schedule_sync_service import ScheduleSyncService

def _render_single_team_pending_cards(pend_df: pd.DataFrame, title_mappings: dict):
    """🏢 단일 팀 진행 중인 작업 카드 렌더링"""
    kst_now_naive = get_current_kst_time().replace(tzinfo=None)
    t_pend = pend_df.copy()
    t_pend["_rank_score"] = t_pend.apply(
        lambda r: get_job_title_rank(title_mappings.get(r["worker_name"]) or r.get("worker_title") or ""),
        axis=1
    )
    t_pend = t_pend.sort_values(by=["_rank_score", "start_time"], ascending=[True, False])

    p_cols = st.columns(4)
    for idx, (_, r) in enumerate(t_pend.iterrows()):
        with p_cols[idx % 4]:
            card_html = get_live_task_card_html(r, title_mappings, kst_now_naive, is_single_view=True)
            st.markdown(card_html, unsafe_allow_html=True)


def _render_kanban_pending_cards(t_pend: pd.DataFrame, title_mappings: dict):
    """🏛️ 전체 팀 칸반 열 진행 중인 작업 카드 렌더링"""
    kst_now_naive = get_current_kst_time().replace(tzinfo=None)
    t_pend_sorted = t_pend.copy()
    t_pend_sorted["_rank_score"] = t_pend_sorted.apply(
        lambda r: get_job_title_rank(title_mappings.get(r["worker_name"]) or r.get("worker_title") or ""),
        axis=1
    )
    t_pend_sorted = t_pend_sorted.sort_values(by=["_rank_score", "start_time"], ascending=[True, False])

    for idx, (_, r) in enumerate(t_pend_sorted.iterrows()):
        card_html = get_live_task_card_html(r, title_mappings, kst_now_naive, is_single_view=False)
        st.markdown(card_html, unsafe_allow_html=True)


def render_live_pending_section(pend_df: pd.DataFrame, selected_team: str, leave_records: list = None):
    """⏳ 진행 중인 작업 섹션 전용 단일 1분 자동 갱신 프래그먼트 (다중 타이머 통합)"""
    # 🏖️ 오늘 휴가 / 연차 / 반차 현황 카드 섹션 (무조건 100%)
    if leave_records:
        st.markdown(f"""<div style="font-size: 15px; font-weight: 800; color: #581c87; border-left: 4px solid #a855f7; padding-left: 9px; margin-bottom: 10px; margin-top: 4px; display: flex; align-items: center; gap: 8px;">🏖️ 오늘 휴가 / 연차 / 반차 현황 <span style="background: #f3e8ff; color: #7e22ce; border-radius: 12px; padding: 2px 8px; font-size: 11.5px; font-weight: 800;">{len(leave_records)}명 부재</span></div>""", unsafe_allow_html=True)
        # 🏛️ 일반 진행/완료 카드와 가로폭(width) 및 크기를 100% 동일하게 맞추기 위해 전체 팀(5열) / 단일 팀(4열) 고정 그리드 사용
        target_cols_count = 5 if selected_team == "전체 팀" else 4
        l_cols = st.columns(target_cols_count)
        for l_idx, l_rec in enumerate(leave_records):
            with l_cols[l_idx % target_cols_count]:
                l_html = get_leave_card_html(l_rec, is_single_view=(selected_team != "전체 팀"))
                st.markdown(l_html, unsafe_allow_html=True)
        st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    st.markdown(f"""<div style="font-size: 17px; font-weight: 800; color: #002d42; border-left: 4px solid #00b4d8; padding-left: 10px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">⏳ 실시간 진행 중인 작업 <span style="background: #e0f2fe; color: #0369a1; border-radius: 12px; padding: 2px 9px; font-size: 12px; font-weight: 800;">{len(pend_df)}건</span></div>""", unsafe_allow_html=True)
    if pend_df.empty:
        st.success("🎉 현재 진행 중인 미완료 작업이 없습니다. 오늘 모든 작업이 성공적으로 완료되었습니다!")
        return

    st.markdown(LIVE_PROGRESS_ANIMATION_AND_TIMER, unsafe_allow_html=True)

    if selected_team == "전체 팀":
        base_teams = ["기술본부", "기술 1팀", "기술 2팀", "기술 3팀", "PI팀"]
        teams_to_render = list(base_teams)
        for extra_t in pend_df["worker_team"].unique():
            if extra_t and not any(is_same_team(extra_t, bt) for bt in teams_to_render):
                teams_to_render.append(extra_t)

        title_mappings = TeamService.get_title_mappings()
        team_cols = st.columns(len(teams_to_render))

        for c_idx, t_name in enumerate(teams_to_render):
            with team_cols[c_idx]:
                theme = get_team_theme(t_name)
                t_pend = pend_df[pend_df["worker_team"].apply(lambda t: is_same_team(t, t_name))]
                cnt_str = f"🟢 {len(t_pend)}건 진행" if len(t_pend) > 0 else "0건"
                cnt_bg = "#d1e7dd" if len(t_pend) > 0 else "#f1f5f9"
                cnt_color = "#0f5132" if len(t_pend) > 0 else "#64748b"
                cnt_border = "#a3cfbb" if len(t_pend) > 0 else "#cbd5e1"

                st.markdown(f"""<div style="background: {theme['bg_gradient']}; border: 1.5px solid {theme['border']}; border-top: 4px solid {theme['primary']}; border-radius: 8px; padding: 10px 8px; margin-bottom: 12px; text-align: center; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);"><div style="display: flex; align-items: center; justify-content: center; gap: 6px; margin-bottom: 5px;"><span style="font-size: 17px;">{theme['icon']}</span><span style="font-size: 15px; font-weight: 800; color: {theme['text_color']}; letter-spacing: -0.3px;">{t_name}</span><span style="background: {theme['primary']}; color: #ffffff; border-radius: 4px; padding: 1px 5px; font-size: 10px; font-weight: 800;">{theme['tag']}</span></div><div><span style="background-color: {cnt_bg}; color: {cnt_color}; border: 1px solid {cnt_border}; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 800;">{cnt_str}</span></div></div>""", unsafe_allow_html=True)

                if t_pend.empty:
                    st.markdown("<div style='background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 26px 8px; text-align: center; color: #94a3b8; font-size: 12px; font-weight: 600; margin-bottom: 10px;'>진행 작업 없음</div>", unsafe_allow_html=True)
                else:
                    _render_kanban_pending_cards(t_pend, title_mappings)
    else:
        title_mappings = TeamService.get_title_mappings()
        theme = get_team_theme(selected_team)
        with st.container(border=True):
            st.markdown(f"""<div style="margin-top: 2px; margin-bottom: 12px; background: {theme['bg_gradient']}; border: 1px solid {theme['border']}; border-left: 6px solid {theme['primary']}; border-radius: 8px; padding: 9px 15px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);"><div style="display: flex; align-items: center; gap: 9px;"><span style="font-size: 18px;">{theme['icon']}</span><span style="font-size: 16px; font-weight: 800; color: {theme['text_color']}; letter-spacing: -0.3px;">{selected_team}</span><span style="background: {theme['primary']}; color: #ffffff; border-radius: 4px; padding: 2px 7px; font-size: 10.5px; font-weight: 800; letter-spacing: -0.2px;">{theme['tag']}</span></div><span style="background-color: #d1e7dd; color: #0f5132; border: 1px solid #a3cfbb; padding: 2.5px 11px; border-radius: 20px; font-size: 11.5px; font-weight: 800;">🟢 {len(pend_df)}건 진행 중</span></div>""", unsafe_allow_html=True)
            _render_single_team_pending_cards(pend_df, title_mappings)


def render_today_live_board(df_raw: pd.DataFrame, team_mappings: dict, selected_team: str = "전체 팀"):
    # 팀명 공백 무관 안전 비교 헬퍼 (예: "기술1팀" == "기술 1팀")
    def is_same_team(t1, t2):
        return str(t1).replace(" ", "").strip() == str(t2).replace(" ", "").strip()

    # 상위 app.py에서 캐시 전처리된 df_raw 활용 (렌더 경로 블로킹 DB 직접 쿼리 제거)

    # 전달된 df_raw의 worker_team 매핑 안전 보장
    if team_mappings and "worker_name" in df_raw.columns:
        df_raw = df_raw.copy()
        df_raw["worker_team"] = df_raw["worker_name"].map(team_mappings).fillna(df_raw.get("worker_team", "")).fillna(UNASSIGNED_TEAM)

    kst_now = get_current_kst_time()
    today_date = kst_now.date()
    kst_now_naive = kst_now.replace(tzinfo=None)

    # 1. 오늘 날짜 데이터 필터링
    if df_raw.empty or "start_time" not in df_raw.columns:
        st.info("현재 등록된 작업 로그 데이터가 없습니다.")
        return

    today_df = df_raw[df_raw["start_time"].dt.date == today_date].copy() if not df_raw.empty else pd.DataFrame()

    # 필수 컬럼 안전 보장 (오늘 작업이 0건이거나 컬럼 누락 시 KeyError 원천 방지)
    for col, default_val in [
        ("status", "COMPLETED"),
        ("worker_team", UNASSIGNED_TEAM),
        ("worker_name", ""),
        ("actual_hours", 0.0),
        ("estimated_hours", 0.0)
    ]:
        if col not in today_df.columns:
            today_df[col] = default_val

    # 팀 필터링 적용
    if selected_team != "전체 팀" and not today_df.empty:
        today_df = today_df[today_df["worker_team"].apply(lambda t: is_same_team(t, selected_team))]

    # 2. 진행 중(PENDING) vs 오늘 완료(COMPLETED) 분리
    if not today_df.empty:
        pend_df = today_df[today_df["status"] == "PENDING"].sort_values("start_time", ascending=False)
        comp_df = today_df[today_df["status"] == "COMPLETED"].sort_values("start_time", ascending=False)
    else:
        pend_df = today_df.iloc[0:0]
        comp_df = today_df.iloc[0:0]

    # 📅 [신규] 아웃룩 스케줄 동기화 및 미래시 승격 (카톡 미보고 작업 자동 진행 & 100% 자동 완료 & 휴가 100%)
    leave_records = []
    try:
        pend_df, auto_comp_df, leave_records = ScheduleSyncService.get_synced_live_tasks(pend_df, comp_df)
        if not auto_comp_df.empty:
            comp_df = pd.concat([comp_df, auto_comp_df], ignore_index=True)
            comp_df = comp_df.drop_duplicates(subset=["worker_name", "start_time", "task_description"], keep="first")
    except Exception as e_sync:
        print(f"[라이브 일정 동기화 예외]: {e_sync}")
        leave_records = []

    # 팀 필터링 재적용 (아웃룩 승격 작업 포함)
    if selected_team != "전체 팀":
        if not pend_df.empty:
            pend_df = pend_df[pend_df["worker_team"].apply(lambda t: is_same_team(t, selected_team))]
        if not comp_df.empty:
            comp_df = comp_df[comp_df["worker_team"].apply(lambda t: is_same_team(t, selected_team))]
        if leave_records:
            leave_records = [l for l in leave_records if is_same_team(l.get("worker_team", ""), selected_team)]

    tot_workers_set = set()
    if not comp_df.empty:
        tot_workers_set.update(comp_df["worker_name"].dropna().unique())
    if not pend_df.empty:
        tot_workers_set.update(pend_df["worker_name"].dropna().unique())
    if leave_records:
        tot_workers_set.update([l["worker_name"] for l in leave_records if l.get("worker_name")])
    tot_workers = len(tot_workers_set)

    tot_comp_h = comp_df["actual_hours"].sum() if "actual_hours" in comp_df.columns else 0.0
    tot_pend_h = pend_df["actual_hours"].sum() if "actual_hours" in pend_df.columns else 0.0
    tot_hours = round(tot_comp_h + tot_pend_h, 1)

    # 3. 상단 실시간 요약 바 (Live Status Summary - 다크모드 NOC 커맨드 센터 스타일)
    summary_html = f"""<div style="background: linear-gradient(135deg, #002233 0%, #003a55 50%, #004d71 100%); border: 1px solid #005f8a; border-radius: 9px; padding: 13px 20px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px; box-shadow: 0 4px 14px rgba(0, 34, 51, 0.25);"><div style="display: flex; align-items: center; gap: 11px;"><span style="background-color: #dc2626; color: #ffffff; border: 1px solid #ef4444; border-radius: 12px; padding: 3px 10px; font-size: 11px; font-weight: 800; letter-spacing: 0.5px; box-shadow: 0 0 8px rgba(220, 38, 38, 0.4);">● LIVE 관제 중</span><span style="font-size: 16.5px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px; text-shadow: 0 1px 3px rgba(0,0,0,0.5);">오늘 ({today_date.strftime('%Y년 %m월 %d일')}) 실시간 현장 지원 현황</span><span style="font-size: 12px; color: #38bdf8; background-color: rgba(0, 180, 216, 0.22); border: 1px solid rgba(56, 189, 248, 0.5); padding: 3px 9px; border-radius: 6px; font-weight: 700;">선택: {selected_team}</span></div><div style="display: flex; align-items: center; gap: 20px; font-size: 13.5px; font-weight: 600;"><span style="color: #cbd5e1;">👥 오늘 투입: <b style="color: #38bdf8; font-size: 14.5px; font-weight: 800;">{tot_workers}명</b></span><span style="color: #cbd5e1;">⏳ 진행 중: <b style="color: #fbbf24; font-size: 14.5px; font-weight: 800;">{len(pend_df)}건</b></span><span style="color: #cbd5e1;">✅ 완료: <b style="color: #4ade80; font-size: 14.5px; font-weight: 800;">{len(comp_df)}건</b></span><span style="color: #cbd5e1;">⏱️ 총 지원 공수: <b style="color: #f472b6; font-size: 14.5px; font-weight: 800;">{tot_hours}시간</b></span></div></div>"""
    st.markdown(summary_html, unsafe_allow_html=True)

    if today_df.empty and pend_df.empty and comp_df.empty:
        st.info(f"☕ 오늘({today_date.strftime('%Y-%m-%d')}) [{selected_team}]에 등록된 작업 보고 또는 일정이 아직 없습니다.")
        return

    # 4 & 5. 🏛️ LIVE 관제 중 하위 전체 내용을 하나로 묶는 대형 통합 네모 컨테이너
    with st.container(border=True):
        st.markdown('<span class="live-board-main-container" style="display:none;"></span>', unsafe_allow_html=True)

        # 4. 실시간 진행 중(PENDING) 작업 섹션 (단일 통합 1분 자동 갱신 + 휴가 100% 카드 포함)
        render_live_pending_section(pend_df, selected_team, leave_records=leave_records)
        st.markdown("<div style='margin-top: 22px; margin-bottom: 20px; border-top: 1.5px solid #e2e8f0;'></div>", unsafe_allow_html=True)

        # 5. 오늘 완료된 작업(COMPLETED) 섹션 (팀 단위 그룹 렌더링)
        st.markdown(f"""<div style="font-size: 17px; font-weight: 800; color: #002d42; border-left: 4px solid #10b981; padding-left: 10px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">✅ 오늘 완료된 작업 <span style="background: #ede9fe; color: #5b21b6; border-radius: 12px; padding: 2px 9px; font-size: 12px; font-weight: 800;">{len(comp_df)}건</span></div>""", unsafe_allow_html=True)
        if comp_df.empty:
            st.info("오늘 완료 보고된 작업이 아직 없습니다.")
        else:
            if selected_team == "전체 팀":
                # 🏛️ 전체 팀 기준: 5개 팀 세로 열 (칸반 보드) 레이아웃
                base_teams = ["기술본부", "기술 1팀", "기술 2팀", "기술 3팀", "PI팀"]
                teams_to_render_comp = list(base_teams)
                for extra_t in comp_df["worker_team"].unique():
                    if extra_t and not any(is_same_team(extra_t, bt) for bt in teams_to_render_comp):
                        teams_to_render_comp.append(extra_t)

                title_mappings = TeamService.get_title_mappings()
                comp_cols = st.columns(len(teams_to_render_comp))

                for c_idx, t_name in enumerate(teams_to_render_comp):
                    with comp_cols[c_idx]:
                        theme = get_team_theme(t_name)
                        t_comp = comp_df[comp_df["worker_team"].apply(lambda t: is_same_team(t, t_name))]
                        cnt_str = f"✅ {len(t_comp)}건 완료" if len(t_comp) > 0 else "0건"
                        cnt_bg = "#ede9fe" if len(t_comp) > 0 else "#f1f5f9"
                        cnt_color = "#5b21b6" if len(t_comp) > 0 else "#64748b"
                        cnt_border = "#c4b5fd" if len(t_comp) > 0 else "#cbd5e1"

                        st.markdown(f"""<div style="background: {theme['bg_gradient']}; border: 1.5px solid {theme['border']}; border-top: 4px solid {theme['primary']}; border-radius: 8px; padding: 10px 8px; margin-bottom: 12px; text-align: center; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);"><div style="display: flex; align-items: center; justify-content: center; gap: 6px; margin-bottom: 5px;"><span style="font-size: 17px;">{theme['icon']}</span><span style="font-size: 15px; font-weight: 800; color: {theme['text_color']}; letter-spacing: -0.3px;">{t_name}</span><span style="background: {theme['primary']}; color: #ffffff; border-radius: 4px; padding: 1px 5px; font-size: 10px; font-weight: 800;">{theme['tag']}</span></div><div><span style="background-color: {cnt_bg}; color: {cnt_color}; border: 1px solid {cnt_border}; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 800;">{cnt_str}</span></div></div>""", unsafe_allow_html=True)

                        if t_comp.empty:
                            st.markdown("<div style='background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 26px 8px; text-align: center; color: #94a3b8; font-size: 12px; font-weight: 600; margin-bottom: 10px;'>완료 작업 없음</div>", unsafe_allow_html=True)
                        else:
                            t_comp = t_comp.copy()
                            t_comp["_rank_score"] = t_comp.apply(lambda r: get_job_title_rank(title_mappings.get(r["worker_name"]) or r.get("worker_title") or ""), axis=1)
                            t_comp = t_comp.sort_values(by=["_rank_score", "start_time"], ascending=[True, False])

                            for idx, (_, r) in enumerate(t_comp.iterrows()):
                                w_name = r["worker_name"]
                                w_title = title_mappings.get(w_name) or r.get("worker_title") or ""
                                title_str = get_job_title_badge(w_title)
                                c_name = r["client_name"]
                                t_desc = r["task_description"]

                                # 🛡️ 아웃룩 일정 고객사명/작업내용 최종 정규화 안전망 (캐시 지연 대비)
                                # 🛡️ 아웃룩 일정 고객사명/작업내용 최종 정규화 안전망 (캐시 지연 대비)
                                if c_name in ["아웃룩 일정", "기타"] or "아웃룩" in str(c_name):
                                    from ...services.client_normalizer import parse_outlook_subject_to_client_and_task
                                    clean_raw = re.sub(r"^\[.*?\]\s*", "", str(t_desc))
                                    pc, pt = parse_outlook_subject_to_client_and_task(clean_raw)
                                    if pc and pc not in ["아웃룩 일정", "기타"]:
                                        c_name = pc
                                        t_desc = pt
                                st_dt = r["start_time"]
                                ed_dt = r["end_time"]
                                st_str = st_dt.strftime("%H:%M") if pd.notna(st_dt) else "?"
                                ed_str = ed_dt.strftime("%H:%M") if pd.notna(ed_dt) else "완료"
                                is_out = (r.get("is_outlook") == True)
                                is_l = bool(r.get("is_leave") == True or "휴가" in str(r.get("log_type", "")) or "연차" in str(r.get("client_name", "")))
                                
                                # 기존 [📅 일정완료], [📅 아웃룩], [일정완료] 등 텍스트 접두사 제거
                                clean_desc = re.sub(r"^\[📅?\s*(일정완료|아웃룩|예정)\]\s*", "", str(t_desc)).strip()

                                if is_l:
                                    source_badge = '<span style="background-color: #f3e8ff; color: #7e22ce; font-size: 9.5px; font-weight: 800; padding: 1px 4px; border-radius: 3px; margin-right: 4px; display: inline-block; vertical-align: middle; white-space: nowrap; flex-shrink: 0;">🏖️</span>'
                                    clean_desc = re.sub(r"^\[(연차|휴가|반차|오전반차|오후반차)\]\s*", "", clean_desc).strip()
                                elif is_out:
                                    source_badge = '<span style="background-color: #0284c7; color: #ffffff; font-size: 10px; font-weight: 900; padding: 1px 4.5px; border-radius: 3px; margin-right: 4px; display: inline-block; vertical-align: middle; white-space: nowrap; flex-shrink: 0; line-height: 1.2;">O</span>'
                                else:
                                    source_badge = '<span style="background-color: #FEE500; color: #371d1e; font-size: 10px; font-weight: 900; padding: 1px 4.5px; border-radius: 3px; margin-right: 4px; display: inline-block; vertical-align: middle; white-space: nowrap; flex-shrink: 0; line-height: 1.2;">K</span>'

                                disp_h = r.get("display_hours")
                                act_h = float(disp_h) if (is_l and pd.notna(disp_h) and float(disp_h) > 0) else r["actual_hours"]
                                comp_border = "#a855f7" if is_l else get_job_title_color(w_title)
                                badge_bg = "#f3e8ff" if is_l else "#ede9fe"
                                badge_c = "#7e22ce" if is_l else "#5b21b6"
                                badge_border = "#d8b4fe" if is_l else "#c4b5fd"
                                badge_icon = "🏖️" if is_l else "✅"
                                clean_desc_tooltip = html.escape(str(clean_desc), quote=True)
                                c_name_tooltip = html.escape(str(c_name), quote=True)
                                comp_html = f"""<div style="background: {'#faf5ff' if is_l else '#ffffff'}; border: 1px solid {'#e9d5ff' if is_l else '#e1e4e8'}; border-left: 4px solid {comp_border}; border-radius: 8px; padding: 9px 10px; margin-bottom: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;"><div><span style="font-size: 13px; font-weight: 700; color: #0f172a;">👤 {w_name}{title_str}</span></div><span style="background-color: {badge_bg}; color: {badge_c}; border: 1px solid {badge_border}; border-radius: 8px; padding: 1px 5px; font-size: 10px; font-weight: 700; white-space: nowrap;">{badge_icon} {st_str}~{ed_str} ({act_h}h)</span></div><div style="font-size: 12px; color: {'#6b21a8' if is_l else '#005073'}; font-weight: 700; margin-bottom: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{c_name_tooltip}">🏢 {c_name}</div><div style="font-size: 11.5px; color: #475569; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{clean_desc_tooltip}">{source_badge}{clean_desc}</div></div>"""
                                st.markdown(comp_html, unsafe_allow_html=True)
            else:
                # 🏢 단일 팀 선택 시: 기존 4열 그리드 레이아웃
                title_mappings = TeamService.get_title_mappings()
                theme = get_team_theme(selected_team)
                with st.container(border=True):
                    st.markdown(f"""<div style="margin-top: 2px; margin-bottom: 10px; background: {theme['bg_gradient']}; border: 1px solid {theme['border']}; border-left: 6px solid {theme['primary']}; border-radius: 8px; padding: 9px 15px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);"><div style="display: flex; align-items: center; gap: 9px;"><span style="font-size: 18px;">{theme['icon']}</span><span style="font-size: 16px; font-weight: 800; color: {theme['text_color']}; letter-spacing: -0.3px;">{selected_team}</span><span style="background: {theme['primary']}; color: #ffffff; border-radius: 4px; padding: 2px 7px; font-size: 10.5px; font-weight: 800; letter-spacing: -0.2px;">{theme['tag']}</span></div><span style="background-color: #ede9fe; color: #5b21b6; border: 1.5px solid #c4b5fd; padding: 2.5px 11px; border-radius: 20px; font-size: 11.5px; font-weight: 800;">✅ {len(comp_df)}건 완료</span></div>""", unsafe_allow_html=True)

                    t_comp = comp_df.copy()
                    t_comp["_rank_score"] = t_comp.apply(lambda r: get_job_title_rank(title_mappings.get(r["worker_name"]) or r.get("worker_title") or ""), axis=1)
                    t_comp = t_comp.sort_values(by=["_rank_score", "start_time"], ascending=[True, False])

                    c_cols = st.columns(4)
                    for idx, (_, r) in enumerate(t_comp.iterrows()):
                        with c_cols[idx % 4]:
                            w_name = r["worker_name"]
                            w_title = title_mappings.get(w_name) or r.get("worker_title") or ""
                            title_str = get_job_title_badge(w_title)
                            c_name = r["client_name"]
                            t_desc = r["task_description"]

                            # 🛡️ 아웃룩 일정 고객사명/작업내용 최종 정규화 안전망 (캐시 지연 대비)
                            if c_name in ["아웃룩 일정", "기타"] or "아웃룩" in str(c_name):
                                from ...services.client_normalizer import parse_outlook_subject_to_client_and_task
                                clean_raw = re.sub(r"^\[.*?\]\s*", "", str(t_desc))
                                pc, pt = parse_outlook_subject_to_client_and_task(clean_raw)
                                if pc and pc not in ["아웃룩 일정", "기타"]:
                                    c_name = pc
                                    t_desc = pt
                            st_dt = r["start_time"]
                            ed_dt = r["end_time"]
                            is_out = (r.get("is_outlook") == True)
                            is_l = bool(r.get("is_leave") == True or "휴가" in str(r.get("log_type", "")) or "연차" in str(r.get("client_name", "")))
                            
                            # 기존 [📅 일정완료], [📅 아웃룩], [일정완료] 등 텍스트 접두사 제거
                            clean_desc = re.sub(r"^\[📅?\s*(일정완료|아웃룩|예정)\]\s*", "", str(t_desc)).strip()

                            if is_l:
                                source_badge = '<span style="background-color: #f3e8ff; color: #7e22ce; font-size: 9.5px; font-weight: 800; padding: 1px 4px; border-radius: 3px; margin-right: 4px; display: inline-block; vertical-align: middle; white-space: nowrap; flex-shrink: 0;">🏖️ 휴가</span>'
                                clean_desc = re.sub(r"^\[(연차|휴가|반차|오전반차|오후반차)\]\s*", "", clean_desc).strip()
                            elif is_out:
                                source_badge = '<span style="background-color: #0284c7; color: #ffffff; font-size: 9.5px; font-weight: 800; padding: 1px 4px; border-radius: 3px; margin-right: 4px; display: inline-block; vertical-align: middle; white-space: nowrap; flex-shrink: 0;">📅 아웃룩</span>'
                            else:
                                source_badge = '<span style="background-color: #FEE500; color: #371d1e; font-size: 9.5px; font-weight: 800; padding: 1px 4px; border-radius: 3px; margin-right: 4px; display: inline-block; vertical-align: middle; white-space: nowrap; flex-shrink: 0;">💬 카톡</span>'

                            disp_h = r.get("display_hours")
                            act_h = float(disp_h) if (is_l and pd.notna(disp_h) and float(disp_h) > 0) else r["actual_hours"]
                            st_str = st_dt.strftime("%H:%M") if pd.notna(st_dt) else "?"
                            ed_str = ed_dt.strftime("%H:%M") if pd.notna(ed_dt) else "완료"
                            comp_border = "#a855f7" if is_l else get_job_title_color(w_title)
                            badge_bg = "#f3e8ff" if is_l else "#ede9fe"
                            badge_c = "#7e22ce" if is_l else "#5b21b6"
                            badge_border = "#d8b4fe" if is_l else "#c4b5fd"
                            badge_icon = "🏖️" if is_l else "✅"

                            clean_desc_tooltip = html.escape(str(clean_desc), quote=True)
                            c_name_tooltip = html.escape(str(c_name), quote=True)

                            comp_html = f"""<div style="background: {'#faf5ff' if is_l else '#ffffff'}; border: 1px solid {'#e9d5ff' if is_l else '#e1e4e8'}; border-left: 4px solid {comp_border}; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;"><div><span style="font-size: 13.5px; font-weight: 700; color: #0f172a;">👤 {w_name}{title_str}</span></div><span style="background-color: {badge_bg}; color: {badge_c}; border: 1px solid {badge_border}; border-radius: 10px; padding: 1px 6px; font-size: 10px; font-weight: 700;">{badge_icon} {st_str}~{ed_str} ({act_h}h)</span></div><div style="font-size: 13px; color: {'#6b21a8' if is_l else '#005073'}; font-weight: 700; margin-bottom: 3px;" title="{c_name_tooltip}">🏢 {c_name}</div><div style="font-size: 12px; color: #475569; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{clean_desc_tooltip}">{source_badge}{clean_desc}</div></div>"""
                            st.markdown(comp_html, unsafe_allow_html=True)


def render_kpi_cards_fragment(kpi_df: pd.DataFrame):
    kpi = StatsService.compute_kpis(kpi_df)
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
            show_kpi_total_hours_dialog(kpi_df)
        
    with kpi_col2:
        st.markdown(f"""
        <div class="kpi-card kpi-card-tasks">
            <div class="kpi-title">📋 총 작업 건수</div>
            <div class="kpi-value" style="color: #0284c7;">{kpi['total_tasks']:,}<span class="kpi-unit">건</span></div>
            <div class="kpi-badge badge-cyan">🟢 완료 {kpi['completed_tasks']}건 <span style="color:#94a3b8;">|</span> 🟡 진행 {kpi['pending_tasks']}건</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button(" ", key="kpi_btn_tasks", use_container_width=True, help="클릭하여 총 작업 건수 상세 팝업 열기"):
            show_kpi_total_tasks_dialog(kpi_df)
        
    with kpi_col3:
        st.markdown(f"""
        <div class="kpi-card kpi-card-workers">
            <div class="kpi-title">👥 투입 인원 & 평균 공수</div>
            <div class="kpi-value" style="color: #4f46e5;">{kpi['active_workers']}<span class="kpi-unit">명</span></div>
            <div class="kpi-badge badge-purple">👤 1인당 평균 {kpi['avg_hours_per_worker']}h</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button(" ", key="kpi_btn_workers", use_container_width=True, help="클릭하여 팀원별 공수 팝업 열기"):
            show_kpi_workers_dialog(kpi_df)
        
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
            show_kpi_urgent_dialog(kpi_df)
        
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
            show_kpi_overdue_dialog(kpi_df)



def render_overwork_banner_fragment(ov_df: pd.DataFrame):
    if not ov_df.empty and "week_label" in ov_df.columns:
        all_rewards = RewardLeaveService.get_all_reward_leaves()
        danger_items = []
        caution_items = []
        rewarded_items = []
        
        # 주차별/팀원별 집계 (주 40시간 / 52시간 과중 근무 감지 시 미래시(SCHEDULED), [교육] 및 [휴가] 구분은 법정 시간에서 제외)
        status_filter = ov_df["status"].isin(["COMPLETED", "PENDING"]) if "status" in ov_df.columns else pd.Series(True, index=ov_df.index)
        log_type_filter = ~ov_df["log_type"].fillna("").astype(str).str.contains("교육|휴가") if "log_type" in ov_df.columns else pd.Series(True, index=ov_df.index)
        df_for_overwork = ov_df[status_filter & log_type_filter]
        wk_user_agg = df_for_overwork.groupby(["worker_name", "week_label"])["actual_hours"].sum().reset_index()
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
                # 🏷️ 과중근무 배너 전용 마커
                st.markdown('<span class="overwork-banner-zone" style="display:none;"></span>', unsafe_allow_html=True)

                # 📊 과중근무 알림 버튼: 실시간 카드 프로그레스 바 타입 스타일링
                st.markdown("""
                <style>
                    /* 불필요한 마커 컨테이너 숨김 */
                    div.element-container:has(.overwork-banner-zone),
                    div.element-container:has(.danger-chip-zone),
                    div.element-container:has(.caution-chip-zone),
                    div.element-container:has(.reward-chip-zone) {
                        display: none !important;
                        height: 0px !important;
                        margin: 0px !important;
                        padding: 0px !important;
                    }

                    /* 🚨 [52h 초과] 레드 프로그레스 바 버튼 타입 */
                    div[data-testid="stColumn"]:has(.danger-chip-zone) div[data-testid="stButton"] > button,
                    div[data-testid="column"]:has(.danger-chip-zone) div[data-testid="stButton"] > button,
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stColumn"]:has(.danger-chip-zone) button,
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) button[kind="primary"] {
                        background: linear-gradient(90deg, #dc2626 0%, #ef4444 100%) !important;
                        background-color: #dc2626 !important;
                        border: 1px solid #b91c1c !important;
                        border-radius: 6px !important;
                        height: 30px !important;
                        min-height: 30px !important;
                        padding: 0 8px !important;
                        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 1px 3px rgba(220, 38, 38, 0.25) !important;
                        cursor: pointer !important;
                        transition: all 0.15s ease-in-out !important;
                    }
                    div[data-testid="stColumn"]:has(.danger-chip-zone) div[data-testid="stButton"] > button:hover,
                    div[data-testid="column"]:has(.danger-chip-zone) div[data-testid="stButton"] > button:hover,
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) button[kind="primary"]:hover {
                        background: linear-gradient(90deg, #b91c1c 0%, #dc2626 100%) !important;
                        border-color: #991b1b !important;
                        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 3px 8px rgba(220, 38, 38, 0.45) !important;
                        transform: translateY(-1px) !important;
                    }

                    /* ⚠️ [40h 초과] 주황색 프로그레스 바 버튼 타입 */
                    div[data-testid="stColumn"]:has(.caution-chip-zone) div[data-testid="stButton"] > button,
                    div[data-testid="column"]:has(.caution-chip-zone) div[data-testid="stButton"] > button,
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stColumn"]:has(.caution-chip-zone) button,
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) button[kind="secondary"],
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div.stButton > button:not([kind="primary"]) {
                        background: linear-gradient(90deg, #ea580c 0%, #f97316 100%) !important;
                        background-color: #ea580c !important;
                        border: 1px solid #c2410c !important;
                        border-radius: 6px !important;
                        height: 30px !important;
                        min-height: 30px !important;
                        padding: 0 8px !important;
                        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 1px 3px rgba(234, 88, 12, 0.25) !important;
                        cursor: pointer !important;
                        transition: all 0.15s ease-in-out !important;
                    }
                    div[data-testid="stColumn"]:has(.caution-chip-zone) div[data-testid="stButton"] > button:hover,
                    div[data-testid="column"]:has(.caution-chip-zone) div[data-testid="stButton"] > button:hover,
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stColumn"]:has(.caution-chip-zone) button:hover {
                        background: linear-gradient(90deg, #c2410c 0%, #ea580c 100%) !important;
                        border-color: #9a3412 !important;
                        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 3px 8px rgba(234, 88, 12, 0.45) !important;
                        transform: translateY(-1px) !important;
                    }

                    /* ✅ [보상 완료] 초록색 프로그레스 바 버튼 타입 */
                    div[data-testid="stColumn"]:has(.reward-chip-zone) div[data-testid="stButton"] > button,
                    div[data-testid="column"]:has(.reward-chip-zone) div[data-testid="stButton"] > button,
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stColumn"]:has(.reward-chip-zone) button {
                        background: linear-gradient(90deg, #16a34a 0%, #22c55e 100%) !important;
                        background-color: #16a34a !important;
                        border: 1px solid #15803d !important;
                        border-radius: 6px !important;
                        height: 30px !important;
                        min-height: 30px !important;
                        padding: 0 8px !important;
                        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 1px 3px rgba(22, 163, 74, 0.25) !important;
                        cursor: pointer !important;
                        transition: all 0.15s ease-in-out !important;
                    }
                    div[data-testid="stColumn"]:has(.reward-chip-zone) div[data-testid="stButton"] > button:hover,
                    div[data-testid="column"]:has(.reward-chip-zone) div[data-testid="stButton"] > button:hover,
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stColumn"]:has(.reward-chip-zone) button:hover {
                        background: linear-gradient(90deg, #15803d 0%, #16a34a 100%) !important;
                        border-color: #166534 !important;
                        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 3px 8px rgba(22, 163, 74, 0.45) !important;
                        transform: translateY(-1px) !important;
                    }

                    /* 📝 프로그레스 바 내부 볼드 화이트 텍스트 + 입체 텍스트 그림자 */
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stButton"] > button *,
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stButton"] > button p,
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.overwork-banner-zone) div[data-testid="stButton"] > button span {
                        color: #ffffff !important;
                        font-weight: 700 !important;
                        font-size: 11.5px !important;
                        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5) !important;
                        letter-spacing: -0.3px !important;
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
                
                # 2행: 🚨 주 52h 초과 위험 팀원들 (있을 경우 - 레드 프로그레스 바)
                if danger_items:
                    col_d_lbl, col_d_chips = st.columns([1.4, 8.6])
                    with col_d_lbl:
                        st.markdown(f"<div style='padding-top:6px; font-size:13px; font-weight:800; color:#dc2626;'>🚨 주 52h 초과 ({len(danger_items)}건):</div>", unsafe_allow_html=True)
                    with col_d_chips:
                        st.markdown('<span class="danger-chip-zone" style="display:none;"></span>', unsafe_allow_html=True)
                        chunk_size = 5
                        for i in range(0, len(danger_items), chunk_size):
                            chunk = danger_items[i:i + chunk_size]
                            d_cols = st.columns(chunk_size)
                            for c_idx, d_item in enumerate(chunk):
                                with d_cols[c_idx]:
                                    st.markdown('<span class="danger-chip-zone" style="display:none;"></span>', unsafe_allow_html=True)
                                    if st.button(
                                        f"🚨 {d_item['worker_name']}({d_item['short_w']}:{d_item['val']}h)",
                                        key=f"btn_chip_danger_{d_item['worker_name']}_{d_item['week_label']}",
                                        type="primary",
                                        use_container_width=True
                                    ):
                                        show_weekly_detail_dialog(d_item["worker_name"], ov_df, default_week_name=d_item["week_label"])

                # 3행: ⚠️ 주 40h 초과 주의 팀원들 (있을 경우 - 오렌지 프로그레스 바)
                if caution_items:
                    col_c_lbl, col_c_chips = st.columns([1.4, 8.6])
                    with col_c_lbl:
                        st.markdown(f"<div style='padding-top:6px; font-size:13px; font-weight:800; color:#d97706;'>⚠️ 주 40h 초과 ({len(caution_items)}건):</div>", unsafe_allow_html=True)
                    with col_c_chips:
                        st.markdown('<span class="caution-chip-zone" style="display:none;"></span>', unsafe_allow_html=True)
                        chunk_size = 5
                        for i in range(0, len(caution_items), chunk_size):
                            chunk = caution_items[i:i + chunk_size]
                            c_cols = st.columns(chunk_size)
                            for c_idx, c_item in enumerate(chunk):
                                with c_cols[c_idx]:
                                    st.markdown('<span class="caution-chip-zone" style="display:none;"></span>', unsafe_allow_html=True)
                                    if st.button(
                                        f"⚠️ {c_item['worker_name']}({c_item['short_w']}:{c_item['val']}h)",
                                        key=f"btn_chip_caution_{c_item['worker_name']}_{c_item['week_label']}",
                                        type="secondary",
                                        use_container_width=True
                                    ):
                                        show_weekly_detail_dialog(c_item["worker_name"], ov_df, default_week_name=c_item["week_label"])

                # 4행: ✅ 과중근무 보상완료 팀원들 (있을 경우 - 그린 프로그레스 바)
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
                                    st.markdown('<span class="reward-chip-zone" style="display:none;"></span>', unsafe_allow_html=True)
                                    if st.button(
                                        f"✅ {r_item['worker_name']}({r_item['short_w']}:{r_item['val']}h)",
                                        key=f"btn_chip_reward_{r_item['worker_name']}_{r_item['week_label']}",
                                        use_container_width=True
                                    ):
                                        show_weekly_detail_dialog(r_item["worker_name"], ov_df, default_week_name=r_item["week_label"])
        else:
            # 🟢 과중 근무자가 없는 경우: 일체형 카드 배너
            st.markdown("""
            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 6px solid #16a34a; border-radius: 8px; padding: 10px 18px; margin: 18px 0 0 0; display: flex; justify-content: space-between; align-items: center; width: 100%; box-sizing: border-box; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);">
                <div style="font-size: 14px; font-weight: 700; color: #0f5132; display: flex; align-items: center; gap: 10px; margin: 0; padding: 0; line-height: 1;">
                    <span style="font-size: 15px; line-height: 1;">🟢</span>
                    <span style="background: #d1e7dd; color: #0f5132; border: 1px solid #a3cfbb; padding: 2px 8px; border-radius: 4px; font-weight: 800; font-size: 12px; line-height: 1.2; display: inline-flex; align-items: center;">[과중 근무 없음]</span>
                    <span style="color: #334155; font-size: 13px; line-height: 1; font-weight: 500;">현재 선택된 기간 내에 주 40시간 / 52시간을 초과한 과중 근무 팀원이 없습니다. (안정적인 근무 상태)</span>
                </div>
            </div>
            """, unsafe_allow_html=True)



def render_home_view(
    df: pd.DataFrame,
    df_raw: pd.DataFrame,
    selected_team: str,
    team_mappings: dict,
    month_desc: str,
    worker_desc: str,
    extra_chips_str: str
):
    """🏠 실시간 분석 대시보드 메인 뷰 (기준패널 + KPI 카드 + 과중업무 배너 + LIVE 관제보드)"""
    # 1. 🏛️ 메인 상단 고시인성 실시간 집계 기준 정보 패널 (과거시 실적 기준)
    criteria_panel_html = (
        f'<div class="active-criteria-container">'
        f'<div class="criteria-left">'
        f'<div class="criteria-header"><span>🔍</span><span>현재 집계 기준</span></div>'
        f'<div class="criteria-chips-wrapper">'
        f'<div class="criteria-chip chip-period"><span class="chip-label">📅 대상 기간:</span><span class="chip-value">{month_desc}</span></div>'
        f'<div class="criteria-chip chip-team"><span class="chip-label">🏢 소속 팀:</span><span class="chip-value">{selected_team}</span></div>'
        f'<div class="criteria-chip chip-worker"><span class="chip-label">👤 담당 팀원:</span><span class="chip-value">{worker_desc}</span></div>'
        f'{extra_chips_str}'
        f'</div>'
        f'</div>'
        f'<div class="criteria-count-badge">'
        f'<span style="color: #22c55e; font-size: 11px;">●</span>'
        f'<span>총 <b>{len(df):,}건</b> 집계 중</span>'
        f'</div>'
        f'</div>'
    )
    st.markdown(criteria_panel_html, unsafe_allow_html=True)

    # 2. 핵심 KPI 5대 카드 (과거시 누적 통계 - 프리미엄 네온 글래스모피즘 - 독립 Fragment)
    render_kpi_cards_fragment(df)

    # 3. 주 40/52시간 초과 과중 업무 배너 (과거시~현재 기준 누적 근무 경고 - 독립 Fragment)
    render_overwork_banner_fragment(df)

    # 4. 과중 근무 배너와 회색선, 회색선과 LIVE 관제 사이 간격 (28px 균일)
    st.markdown("<div style='margin-top: 28px; margin-bottom: 28px; border-top: 1.5px solid #cbd5e1;'></div>", unsafe_allow_html=True)

    # 5. 🟢 오늘 실시간 작업 현황 라이브 보드 (현재시: LIVE 관제)
    render_today_live_board(df_raw, team_mappings, selected_team)

    # 6. 📏 LIVE 관제 카드 아래와 미래시 일정표 사이 20px 대칭 구분선
    st.markdown("""
    <div class="live-to-calendar-divider" style="margin-top: 20px; margin-bottom: 20px; border-top: 1.5px solid #cbd5e1; width: 100%;"></div>
    """, unsafe_allow_html=True)

    # 7. 🌟 📅 월간캘린더 통합 일정표 (동기화: 아웃룩&Teams 캘린더 - 프리미엄 NOC 헤더 바)
    cal_header_html = f"""<div style="background: linear-gradient(135deg, #002233 0%, #003a55 50%, #004d71 100%); border: 1px solid #005f8a; border-radius: 9px; padding: 13px 20px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px; box-shadow: 0 4px 14px rgba(0, 34, 51, 0.25);"><div style="display: flex; align-items: center; gap: 11px;"><span style="background-color: #0284c7; color: #ffffff; border: 1px solid #38bdf8; border-radius: 12px; padding: 3px 10px; font-size: 11px; font-weight: 800; letter-spacing: 0.5px; box-shadow: 0 0 8px rgba(2, 132, 199, 0.4);">● 월간캘린더</span><span style="font-size: 16.5px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px; text-shadow: 0 1px 3px rgba(0,0,0,0.5);">통합 일정표</span><span style="font-size: 12px; color: #38bdf8; background-color: rgba(0, 180, 216, 0.22); border: 1px solid rgba(56, 189, 248, 0.5); padding: 3px 9px; border-radius: 6px; font-weight: 700;">동기화: 아웃룩&Teams 캘린더</span></div><div style="display: flex; align-items: center; gap: 20px; font-size: 13.5px; font-weight: 600;"><span style="color: #cbd5e1;">👥 등록 인원: <b style="color: #38bdf8; font-size: 14.5px; font-weight: 800;">7명</b></span><span style="color: #cbd5e1;">🔄 연동 주기: <b style="color: #4ade80; font-size: 14.5px; font-weight: 800;">10분 자동</b></span><span style="color: #cbd5e1;">📅 일정 뷰: <b style="color: #fbbf24; font-size: 14.5px; font-weight: 800;">월간 캘린더</b></span></div></div>"""
    st.markdown(cal_header_html, unsafe_allow_html=True)

    with st.container(border=True):
        try:
            render_outlook_calendar_widget()
        except Exception as e_cal:
            st.info("📅 기술본부 아웃룩 일정을 동기화하는 중입니다. (잠시 후 새로고침 시 정상 반영됩니다)")
