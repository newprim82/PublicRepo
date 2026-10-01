# -*- coding: utf-8 -*-
import re
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List

try:
    from src.services.email_schedule_service import EmailScheduleService
    from src.auth.auth_manager import AuthManager
    from src.services.email_sender import EmailSender
except ImportError:
    from ...services.email_schedule_service import EmailScheduleService
    from ...auth.auth_manager import AuthManager
    from ...services.email_sender import EmailSender


def render_email_schedule_view():
    """
    📬 [정기 메일 발송 대상 관리] 메인 뷰 (Cisco ACI 테마 표준 100% 준수)
    - 매주 월요일 오전 08:00 정기 자동 발송 대상 수신자 관리
    - 신규 수신자(예: khkim@sangsanginworld.co.kr) 등록 및 즉시 연동
    - 예상 비용산정 대시보드 및 정산 엑셀 포함 권한(화이트리스트) 자동 연동
    - 활성화/비활성화 스위치 및 삭제 관리
    """
    st.markdown("""
    <style>
    /* 🏛️ Cisco ACI 표준 테마: 정기 메일 대상 관리 스타일 */
    .schedule-main-title {
        font-size: 21px !important;
        font-weight: 800 !important;
        color: #002d42 !important;
        letter-spacing: -0.4px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .schedule-main-desc {
        font-size: 13px !important;
        color: #475569 !important;
        margin-top: 4px;
        font-weight: 500;
        line-height: 1.5;
    }
    .schedule-kpi-row {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-top: 14px;
        margin-bottom: 20px;
    }
    .schedule-kpi-card {
        background: #ffffff;
        border: 1.2px solid #e2e8f0;
        border-radius: 8px;
        padding: 14px 16px;
        box-shadow: 0 1px 3px rgba(0, 45, 66, 0.05);
        border-top: 3.5px solid #005073;
    }
    .schedule-kpi-card.top-blue { border-top-color: #0284c7; }
    .schedule-kpi-card.top-green { border-top-color: #10b981; }
    .schedule-kpi-card.top-purple { border-top-color: #8b5cf6; }
    .schedule-kpi-label {
        font-size: 12px;
        font-weight: 700;
        color: #64748b;
        margin-bottom: 4px;
    }
    .schedule-kpi-val {
        font-size: 20px;
        font-weight: 900;
        color: #002d42;
        letter-spacing: -0.5px;
    }
    .schedule-kpi-sub {
        font-size: 11px;
        color: #94a3b8;
        margin-top: 3px;
        font-weight: 600;
    }
    /* 🏛️ 신규 수신자 등록 폼 카드 스타일링 */
    div[data-testid="stForm"] {
        background: #ffffff !important;
        border: 1.5px solid #cbd5e1 !important;
        border-radius: 8px !important;
        padding: 20px 24px !important;
        margin-bottom: 22px !important;
        box-shadow: 0 2px 8px rgba(0, 45, 66, 0.04) !important;
    }
    div[data-testid="stForm"] label,
    div[data-testid="stForm"] [data-testid="stWidgetLabel"] p,
    div[data-testid="stForm"] label p {
        color: #002d42 !important;
        font-weight: 700 !important;
        font-size: 13px !important;
        letter-spacing: -0.2px !important;
    }
    div[data-testid="stForm"] [data-testid="stCheckbox"] label span {
        color: #002d42 !important;
        font-weight: 700 !important;
        font-size: 13px !important;
    }
    .schedule-badge-active {
        background: #dcfce7;
        color: #15803d;
        font-weight: 800;
        font-size: 11.5px;
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid #bbf7d0;
    }
    .schedule-badge-inactive {
        background: #f1f5f9;
        color: #94a3b8;
        font-weight: 700;
        font-size: 11.5px;
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid #e2e8f0;
    }
    </style>
    """, unsafe_allow_html=True)

    # 1. 헤더 타이틀 및 설명
    st.markdown("""
    <div>
        <div class="schedule-main-title">
            <span>📬</span><span>정기 메일 발송 대상 관리 (주간 실적 & 예상 비용산정)</span>
        </div>
        <div class="schedule-main-desc">
            <b>매주 월요일 오전 08:00</b>에 정기적으로 발송되는 업무 실적 Summary 및 예상 비용산정 대시보드 리포트의 수신 대상자를 관리합니다.<br>
            이곳에 등록된 수신자는 <b>비용산정 대외비 리포트(본문 및 엑셀 개인장표)</b>를 안전하게 받아볼 수 있도록 인가 화이트리스트에 자동 연동됩니다.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. 데이터 로드 및 통계
    recipients = EmailScheduleService.get_all_recipients()
    tot_cnt = len(recipients)
    active_cnt = sum(1 for r in recipients if r.get("is_active", True))
    cost_cnt = sum(1 for r in recipients if r.get("include_cost", True) and r.get("is_active", True))

    st.markdown(f"""
    <div class="schedule-kpi-row">
        <div class="schedule-kpi-card">
            <div class="schedule-kpi-label">👥 총 등록 수신자</div>
            <div class="schedule-kpi-val">{tot_cnt}명</div>
            <div class="schedule-kpi-sub">정기 발송 풀에 등록된 인원</div>
        </div>
        <div class="schedule-kpi-card top-blue">
            <div class="schedule-kpi-label">🚀 실시간 활성 대상</div>
            <div class="schedule-kpi-val" style="color: #0284c7;">{active_cnt}명</div>
            <div class="schedule-kpi-sub">차주 월요일 08:00 발송 예정</div>
        </div>
        <div class="schedule-kpi-card top-green">
            <div class="schedule-kpi-label">💰 비용산정 포함 대상</div>
            <div class="schedule-kpi-val" style="color: #10b981;">{cost_cnt}명</div>
            <div class="schedule-kpi-sub">예상 청구금액 및 정산 엑셀 포함</div>
        </div>
        <div class="schedule-kpi-card top-purple">
            <div class="schedule-kpi-label">⏰ 기본 발송 주기</div>
            <div class="schedule-kpi-val" style="color: #8b5cf6; font-size: 17px;">매주 월 08:00</div>
            <div class="schedule-kpi-sub">배치 스케줄러 자동 가동</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    is_auth = AuthManager.is_authenticated()

    # 3. 신규 수신자 등록 카드 (관리자 권한 가드)
    st.markdown("""
    <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
        <span>➕</span><span>신규 정기 발송 수신자 추가 등록</span>
    </div>
    """, unsafe_allow_html=True)

    if not is_auth:
        st.info("💡 신규 수신자 등록 및 수정/삭제는 **시스템 관리자 로그인** 후 이용하실 수 있습니다.")
    else:
        with st.form("form_schedule_recipient_add", clear_on_submit=False):
            col_f1, col_f2, col_f3 = st.columns([2.5, 1.5, 1.5])
            with col_f1:
                input_email = st.text_input("수신 이메일 주소 *", placeholder="khkim@sangsanginworld.co.kr", key="sched_input_email")
            with col_f2:
                input_name = st.text_input("성명 / 직함", placeholder="김경현 수석", key="sched_input_name")
            with col_f3:
                input_dept = st.text_input("소속 부서 / 팀", placeholder="기술 1팀", key="sched_input_dept")

            col_sub1, col_sub2 = st.columns([4, 1.2])
            with col_sub1:
                input_note = st.text_input("비고 / 전달 사유 (선택)", placeholder="정기 주간 업무 실적 및 예상 비용산정 리포트 공유", key="sched_input_note")
            with col_sub2:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                input_include_cost = st.checkbox("비용산정 포함", value=True, help="체크 시 예상 청구 금액 대시보드와 정산 엑셀(개인장표 포함)이 함께 발송됩니다.", key="sched_input_cost")

            col_btn, _ = st.columns([1.5, 3])
            with col_btn:
                submit_btn = st.form_submit_button("➕ 정기 수신자 등록", type="primary", use_container_width=True)
                if submit_btn:
                    clean_email = (input_email or "").strip()
                    if not clean_email:
                        st.warning("이메일 주소를 입력해주세요.")
                    else:
                        ok, msg = EmailScheduleService.add_recipient(
                            email=clean_email,
                            name=(input_name or "").strip(),
                            department=(input_dept or "").strip(),
                            schedule_cron="매주 월요일 08:00",
                            include_cost=input_include_cost,
                            is_active=True,
                            note=(input_note or "").strip()
                        )
                        if ok:
                            st.success(msg)
                            st.toast(msg, icon="✅")
                            st.rerun()
                        else:
                            st.error(msg)

    # 4. 등록된 정기 메일 발송 수신자 목록 테이블
    st.markdown("""
    <div style="font-size: 15px; font-weight: 800; color: #002d42; margin-top: 10px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 6px;">
            <span>📋</span><span>현재 등록된 정기 발송 수신자 리스트</span>
        </div>
        <span style="font-size: 12px; color: #64748b; font-weight: 600;">클라우드 DB 실시간 동기화 중</span>
    </div>
    """, unsafe_allow_html=True)

    if not recipients:
        st.warning("등록된 정기 메일 수신자가 없습니다.")
        return

    # 테이블 렌더링
    for idx, r in enumerate(recipients, start=1):
        em = r["email"]
        nm = r.get("name", "") or "-"
        dept = r.get("department", "") or "-"
        cron = r.get("schedule_cron", "매주 월요일 08:00")
        is_act = r.get("is_active", True)
        inc_cost = r.get("include_cost", True)
        note = r.get("note", "") or ""
        created_str = str(r.get("created_at", ""))[:16]

        status_badge = '<span class="schedule-badge-active">● 활성화 (발송 중)</span>' if is_act else '<span class="schedule-badge-inactive">○ 일시 중지</span>'
        cost_badge = '<span style="color: #0284c7; font-weight: 800; font-size: 11.5px; background: #e0f2fe; padding: 2px 7px; border-radius: 4px;">💰 비용 포함</span>' if inc_cost else '<span style="color: #64748b; font-size: 11.5px; background: #f1f5f9; padding: 2px 7px; border-radius: 4px;">실적만</span>'

        with st.container():
            st.markdown(f"""
            <div style="background: #ffffff; border: 1.2px solid {'#bae6fd' if is_act else '#e2e8f0'}; border-left: 4.5px solid {'#0284c7' if is_act else '#94a3b8'}; border-radius: 8px; padding: 12px 18px; margin-bottom: 8px; box-shadow: 0 1px 4px rgba(0,45,66,0.03);">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-weight: 800; color: #002d42; font-size: 14px;">#{idx}</span>
                        <span style="font-weight: 900; color: #002d42; font-size: 14.5px;">{em}</span>
                        <span style="color: #475569; font-weight: 700; font-size: 13px;">({nm} | {dept})</span>
                        {status_badge}
                        {cost_badge}
                    </div>
                    <div style="font-size: 11.5px; color: #64748b;">
                        <span>⏰ {cron}</span>
                        <span style="margin: 0 6px;">|</span>
                        <span>등록: {created_str}</span>
                    </div>
                </div>
                {f'<div style="margin-top: 6px; font-size: 12px; color: #64748b;">📌 비고: {note}</div>' if note else ''}
            </div>
            """, unsafe_allow_html=True)

            if is_auth:
                col_act1, col_act2, _ = st.columns([1.2, 1, 4])
                with col_act1:
                    toggle_label = "⏸️ 발송 일시 중지" if is_act else "▶️ 발송 재개"
                    if st.button(toggle_label, key=f"btn_toggle_{em}", use_container_width=True):
                        ok, msg = EmailScheduleService.toggle_active(em)
                        if ok:
                            st.toast(msg, icon="🔄")
                            st.rerun()
                        else:
                            st.error(msg)
                with col_act2:
                    if em != "ymmoon@sangsanginworld.co.kr":
                        if st.button("🗑️ 삭제", key=f"btn_del_{em}", use_container_width=True):
                            ok, msg = EmailScheduleService.delete_recipient(em)
                            if ok:
                                st.toast(msg, icon="🗑️")
                                st.rerun()
                            else:
                                st.error(msg)

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # 5. 안내 배너
    st.markdown("""
    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 18px; font-size: 12.5px; color: #475569; line-height: 1.6;">
        💡 <b>정기 발송 동작 안내</b><br>
        1. 본 리스트에 등록된 수신자는 매주 월요일 오전 08:00 배치 스케줄러(<code>send_weekly_report.py</code>) 가동 시 자동으로 수신 대상에 포함됩니다.<br>
        2. 수신자가 추가 등록되면 <b>'예상 비용산정 대시보드' 보안 인가 목록(화이트리스트)</b>에도 즉시 반영되어 동일한 리포트가 안전하게 전송됩니다.<br>
        3. 일시적으로 수신을 중단해야 할 경우, 삭제하지 않고 <code>[⏸️ 발송 일시 중지]</code> 버튼을 눌러 비활성화할 수 있습니다.
    </div>
    """, unsafe_allow_html=True)
