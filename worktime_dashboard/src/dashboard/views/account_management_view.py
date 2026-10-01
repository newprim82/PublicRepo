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
    - 등록된 계정 비밀번호 변경 및 삭제 관리
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
        margin-bottom: 6px !important;
    }
    .account-hero-desc {
        font-size: 13.5px !important;
        color: #000000 !important;
        font-weight: 500 !important;
        line-height: 1.6 !important;
    }
    .account-card-box {
        background: #ffffff !important;
        border: 1.5px solid #cbd5e1 !important;
        border-radius: 8px !important;
        padding: 18px 22px !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05) !important;
    }
    label,
    div[data-testid="stWidgetLabel"] p,
    div[data-testid="stWidgetLabel"] span,
    div[data-testid="stWidgetLabel"] * {
        color: #000000 !important;
        font-weight: 800 !important;
        font-size: 13.5px !important;
    }
    div[data-baseweb="input"],
    div[data-baseweb="base-input"] {
        background-color: #ffffff !important;
        background: #ffffff !important;
        border: 1.5px solid #94a3b8 !important;
        border-radius: 6px !important;
    }
    div[data-baseweb="input"] input,
    div[data-baseweb="base-input"] input {
        color: #000000 !important;
        font-weight: 700 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # 1. Hero Section
    st.markdown("""
    <div class="account-hero">
        <div class="account-hero-title">
            <span>👤</span>
            <span>시스템 관리자 계정 관리 (Super Admin 전용)</span>
        </div>
        <div class="account-hero-desc">
            대시보드에 로그인할 수 있는 관리자 계정을 신규 등록하고 관리합니다.<br>
            • <b>newprim (Super Admin)</b>: 모든 메뉴 및 시스템 관리, 계정 등록/관리 등 전체 권한 보유<br>
            • <b>신규 등록 계정 (Admin)</b>: 작업 원장, 통계 분석, 실적 관리 등 일반 관리 권한 보유 (시스템 관리 메뉴는 자동 숨김 처리)
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_create, col_list = st.columns([1.0, 1.2], gap="large")

    # 2. 신규 계정 등록 폼
    with col_create:
        st.markdown("<h4 style='color: #000000; font-weight: 900;'>➕ 신규 관리자(Admin) 계정 등록</h4>", unsafe_allow_html=True)
        
        with st.container():
            st.markdown('<div class="account-card-box">', unsafe_allow_html=True)
            
            new_u = st.text_input("아이디 (Username):", key="acc_new_username", placeholder="예: admin_kim")
            new_p = st.text_input("비밀번호 (Password):", type="password", key="acc_new_password", placeholder="최소 4자 이상")
            new_name = st.text_input("담당자 성명:", key="acc_new_name", placeholder="예: 김철수 대리")
            new_note = st.text_input("비고 (소속/용도):", key="acc_new_note", placeholder="예: 기술1팀 운영 관리자")
            
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            
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
            
            st.markdown('</div>', unsafe_allow_html=True)

    # 3. 등록된 관리자 계정 목록 및 관리
    with col_list:
        st.markdown("<h4 style='color: #000000; font-weight: 900;'>👥 등록된 관리자 계정 목록</h4>", unsafe_allow_html=True)
        
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
                    '<span style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: #ffffff; padding: 2.5px 8px; border-radius: 4px; font-size: 11px; font-weight: 800;">👑 Super Admin</span>'
                    if is_super else
                    '<span style="background: #0284c7; color: #ffffff; padding: 2.5px 8px; border-radius: 4px; font-size: 11px; font-weight: 800;">🛡️ Admin</span>'
                )

                card_html = f"""
                <div style="background: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 8px; padding: 13px 18px; margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.05);">
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 8px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            {role_badge}
                            <span style="color: #000000; font-weight: 800; font-size: 14px;">{un}</span>
                            <span style="color: #475569; font-size: 12.5px; font-weight: 600;">({name or '성명 미등록'})</span>
                        </div>
                        <div style="color: #64748b; font-size: 11px; font-weight: 600;">
                            등록일: {dt}
                        </div>
                    </div>
                    <div style="font-size: 12px; color: #475569; margin-bottom: 6px;">
                        • 비고: <span style="color: #000000; font-weight: 600;">{note or '-'}</span>
                    </div>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)

                # 비밀번호 변경 및 삭제 제어 (Super Admin 본인은 삭제 불가)
                with st.expander(f"⚙️ [{un}] 계정 관리 (비밀번호 변경 / 삭제)", expanded=False):
                    edit_c1, edit_c2 = st.columns([1.2, 0.8])
                    with edit_c1:
                        new_pwd_input = st.text_input("새 비밀번호:", type="password", key=f"edit_pwd_{un}")
                        if st.button("비밀번호 변경", key=f"btn_edit_pwd_{un}"):
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
                            st.markdown("<div style='color: #64748b; font-size: 11.5px; margin-top: 25px;'>🔒 Super Admin 계정은 삭제할 수 없습니다.</div>", unsafe_allow_html=True)
                        else:
                            st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
                            if st.button(f"🗑️ 계정 삭제", key=f"btn_del_{un}", type="secondary"):
                                succ, msg = AuthManager.delete_account(un)
                                if succ:
                                    st.toast(msg, icon="✅")
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
