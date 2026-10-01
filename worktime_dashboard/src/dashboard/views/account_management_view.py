# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime

from ...auth.auth_manager import AuthManager, SUPER_ADMIN_USERNAME


def render_account_management_view():
    """
    👤 [시스템 계정 관리] 메인 뷰 (Super Admin 전용 메뉴)
    - newprim (Super Admin)만 접근 가능
    - 일반 관리자(Admin) 계정 신규 생성/등록
    - 등록된 계정 비밀번호 변경 및 삭제 관리 (체크박스 선택 기반)
    - PBKDF2 단방향 솔트 해시 암호화 적용 안내
    - 흰색 바탕 100% 고대비 블랙 텍스트 표준 준수
    """
    # 🔒 Super Admin 보안 가드: newprim이 아니면 접근 전면 차단
    if not AuthManager.is_super_admin():
        st.markdown("""
        <div style="background: #ffffff; border: 2px solid #ef4444; border-left: 6px solid #ef4444; border-radius: 10px; padding: 22px 26px; margin: 20px 0; box-shadow: 0 2px 10px rgba(239, 68, 68, 0.1);">
            <div style="font-size: 18px; font-weight: 900; color: #b91c1c; display: flex; align-items: center; gap: 8px;">
                <span>⛔</span> <span>접근 권한 제한 (Super Admin 전용)</span>
            </div>
            <div style="font-size: 13.5px; color: #000000; font-weight: 600; margin-top: 8px; line-height: 1.6;">
                본 메뉴는 시스템 최고 관리자(<b>Super Admin: newprim</b>) 계정으로 로그인한 경우에만 조회 및 관리가 가능합니다.<br>
                일반 관리자(Admin) 계정은 시스템 관리 메뉴 및 계정 등록 메뉴에 접근할 수 없습니다.
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    st.markdown("""
    <style>
    /* ☀️ 흰색 바탕 고대비 절대 가독성 보장 스타일 */
    .account-hero {
        background: #ffffff !important;
        border: 1.5px solid #0284c7 !important;
        border-left: 6px solid #0284c7 !important;
        border-radius: 10px !important;
        padding: 18px 24px !important;
        margin-bottom: 22px !important;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06) !important;
    }
    .account-hero-title {
        font-size: 21px !important;
        font-weight: 900 !important;
        color: #000000 !important;
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
        margin-bottom: 8px !important;
    }
    .account-hero-desc {
        font-size: 13px !important;
        color: #000000 !important;
        font-weight: 500 !important;
        line-height: 1.65 !important;
    }
    .account-security-badge {
        display: inline-block !important;
        background: #f0fdf4 !important;
        border: 1px solid #86efac !important;
        color: #166534 !important;
        padding: 3px 8px !important;
        border-radius: 4px !important;
        font-weight: 800 !important;
        font-size: 11.5px !important;
        margin-right: 6px !important;
    }

    /* ☀️ 흰색 네모 카드 박스 (Border Container) 스타일 강제 */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff !important;
        background: #ffffff !important;
        border: 1.5px solid #cbd5e1 !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04) !important;
        padding: 18px 22px !important;
        margin-bottom: 14px !important;
    }

    /* ☀️ 모든 입력창 흰색 배경 & 100% 검은색 글자 강제 */
    div[data-testid="stTextInput"] input,
    div[data-baseweb="input"] input,
    div[data-baseweb="base-input"] input,
    input[type="text"],
    input[type="password"] {
        background-color: #ffffff !important;
        background: #ffffff !important;
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        font-weight: 700 !important;
        font-size: 13.5px !important;
    }

    div[data-baseweb="input"],
    div[data-baseweb="base-input"],
    div[data-testid="stTextInput"] > div {
        background-color: #ffffff !important;
        background: #ffffff !important;
        border: 1.5px solid #94a3b8 !important;
        border-radius: 6px !important;
    }

    div[data-testid="stTextInput"] input::placeholder {
        color: #64748b !important;
        -webkit-text-fill-color: #64748b !important;
        font-weight: 500 !important;
    }

    /* 라벨 및 텍스트 검정색 유지 */
    label,
    div[data-testid="stWidgetLabel"] p,
    div[data-testid="stWidgetLabel"] span {
        color: #000000 !important;
        font-weight: 800 !important;
        font-size: 13.5px !important;
    }

    /* 체크박스 스타일 */
    div[data-testid="stCheckbox"] {
        margin-top: 2px !important;
    }
    div[data-testid="stCheckbox"] label span {
        color: #000000 !important;
        font-weight: 700 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # 1. Hero Section (암호화 방식 설명 포함)
    st.markdown("""
    <div class="account-hero">
        <div class="account-hero-title">
            <span>👤</span>
            <span>시스템 관리자 계정 관리 (Super Admin 전용)</span>
        </div>
        <div class="account-hero-desc">
            대시보드에 로그인할 수 있는 관리자 계정을 신규 등록하고 관리합니다.<br>
            • <b>newprim (Super Admin)</b>: 모든 메뉴 및 시스템 관리, 계정 등록/관리 등 전체 권한 보유<br>
            • <b>신규 등록 계정 (Admin)</b>: 작업 원장, 통계 분석, 실적 관리 등 일반 관리 권한 보유 (시스템 관리 메뉴는 자동 숨김 처리)<br>
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #bae6fd;">
                <span class="account-security-badge">🛡️ 비밀번호 보안 방식</span>
                <b>PBKDF2-HMAC-SHA256 (100,000회 반복 솔트 해시)</b> 단방향 암호화 적용<br>
                <span style="color: #475569; font-size: 12px; margin-left: 4px;">
                    ※ 복호화 키 자체가 존재하지 않는 단방향 믹서기 구조로, 서버 소스코드나 DB가 유출되어도 원래 비밀번호를 절대 복원할 수 없습니다.
                </span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_create, col_list = st.columns([1.0, 1.2], gap="large")

    # 2. 신규 계정 등록 폼 (흰색 네모 박스 안)
    with col_create:
        st.markdown("<h4 style='color: #000000; font-weight: 900; margin-bottom: 12px;'>➕ 신규 관리자(Admin) 계정 등록</h4>", unsafe_allow_html=True)
        
        with st.container(border=True):
            new_u = st.text_input("아이디 (Username):", key="acc_new_username", placeholder="예: admin_kim")
            new_p = st.text_input("비밀번호 (Password):", type="password", key="acc_new_password", placeholder="최소 4자 이상")
            new_name = st.text_input("담당자 성명:", key="acc_new_name", placeholder="예: 김철수 대리")
            new_note = st.text_input("비고 (소속/용도):", key="acc_new_note", placeholder="예: 기술1팀 운영 관리자")
            
            st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
            
            if st.button("➕ 신규 관리자 계정 등록", type="primary", use_container_width=True, key="btn_create_account"):
                if not new_u or not new_p:
                    st.error("아이디와 비밀번호를 모두 입력해주세요.")
                else:
                    succ, msg = AuthManager.create_account(
                        username=new_u,
                        password=new_p,
                        name=new_name,
                        note=new_note
                    )
                    if succ:
                        st.toast(msg, icon="✅")
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    # 3. 등록된 관리자 계정 목록 (맨 앞 네모박스 체크 시 계정 제어 패널 노출)
    with col_list:
        st.markdown("<h4 style='color: #000000; font-weight: 900; margin-bottom: 12px;'>👥 등록된 관리자 계정 목록</h4>", unsafe_allow_html=True)
        
        accounts = AuthManager.get_all_accounts(force_reload=True)
        
        if not accounts:
            st.info("등록된 계정이 없습니다.")
        else:
            for acc in accounts:
                un = acc.get("username", "")
                name = acc.get("name", "")
                role = acc.get("role", "ADMIN")
                note = acc.get("note", "")
                dt = acc.get("created_at", "")[:16]
                is_super = (un.lower() == SUPER_ADMIN_USERNAME.lower())

                role_badge = (
                    '<span style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: #ffffff; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 800;">👑 Super Admin</span>'
                    if is_super else
                    '<span style="background: #0284c7; color: #ffffff; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 800;">🛡️ Admin</span>'
                )

                # 각 계정을 흰색 네모 박스로 감싸고 맨 앞에 체크박스 배치
                with st.container(border=True):
                    c_chk, c_badge, c_info = st.columns([0.08, 0.32, 0.60], vertical_alignment="center")
                    
                    with c_chk:
                        is_manage_selected = st.checkbox("선택", key=f"chk_manage_{un}", label_visibility="collapsed")
                    with c_badge:
                        st.markdown(role_badge, unsafe_allow_html=True)
                    with c_info:
                        st.markdown(
                            f"<span style='color: #000000; font-weight: 900; font-size: 15px;'>{un}</span> "
                            f"<span style='color: #475569; font-size: 12.5px; font-weight: 600;'>({name or '성명 미등록'})</span>",
                            unsafe_allow_html=True
                        )

                    # 등록일 및 비고
                    st.markdown(f"""
                    <div style="font-size: 12px; color: #475569; margin: 4px 0 0 28px;">
                        <span>• 비고: <b style="color: #000000;">{note or '-'}</b></span>
                        <span style="margin-left: 12px; color: #64748b;">(등록일: {dt})</span>
                    </div>
                    """, unsafe_allow_html=True)

                    # ✅ 맨 앞 네모박스(체크박스)를 체크했을 때만 계정 관리 패널 열림!
                    if is_manage_selected:
                        st.markdown("<div style='border-top: 1.5px dashed #cbd5e1; margin: 12px 0 10px 0;'></div>", unsafe_allow_html=True)
                        st.markdown(f"<div style='font-size: 13px; font-weight: 900; color: #0284c7; margin-bottom: 8px;'>⚙️ [{un}] 계정 제어 패널</div>", unsafe_allow_html=True)
                        
                        edit_c1, edit_c2 = st.columns([1.2, 0.8], gap="medium")
                        with edit_c1:
                            new_pwd_input = st.text_input("새 비밀번호:", type="password", key=f"edit_pwd_{un}", placeholder="변경할 새 비밀번호")
                            if st.button("🔑 비밀번호 변경", key=f"btn_edit_pwd_{un}", use_container_width=True):
                                if not new_pwd_input:
                                    st.error("새 비밀번호를 입력해주세요.")
                                else:
                                    succ, msg = AuthManager.update_account_password(un, new_pwd_input)
                                    if succ:
                                        st.toast(msg, icon="✅")
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)
                        with edit_c2:
                            if is_super:
                                st.markdown("<div style='background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; margin-top: 22px; color: #64748b; font-size: 11.5px; font-weight: 700; text-align: center;'>🔒 Super Admin 계정은<br>삭제할 수 없습니다.</div>", unsafe_allow_html=True)
                            else:
                                st.markdown("<div style='height: 22px;'></div>", unsafe_allow_html=True)
                                if st.button(f"🗑️ 계정 삭제", key=f"btn_del_{un}", type="secondary", use_container_width=True):
                                    succ, msg = AuthManager.delete_account(un)
                                    if succ:
                                        st.toast(msg, icon="✅")
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)
