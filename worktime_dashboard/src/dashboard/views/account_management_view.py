# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime

from ...auth.auth_manager import AuthManager, SUPER_ADMIN_USERNAME


def render_account_management_view():
    """
    👤 [시스템 계정 관리] 메인 뷰 (Cisco 테마 표준 적용)
    - newprim (Super Admin)만 접근 가능
    - 일반 관리자(Admin) 계정 신규 생성/등록 (표준 st.form 활용)
    - 등록된 계정 체크박스 선택 기반 비밀번호 변경 및 삭제 관리
    - PBKDF2 단방향 솔트 해시 암호화 방식 안내
    """
    # 🔒 Super Admin 보안 가드: newprim이 아니면 접근 전면 차단
    if not AuthManager.is_super_admin():
        st.markdown("""
        <div style="background: #ffffff; border: 1.2px solid #fee2e2; border-left: 4.5px solid #ef4444; border-radius: 8px; padding: 18px 22px; margin: 15px 0; box-shadow: 0 1px 4px rgba(0,0,0,0.04);">
            <div style="font-size: 16px; font-weight: 800; color: #b91c1c; display: flex; align-items: center; gap: 8px;">
                <span>⛔</span> <span>접근 권한 제한 (Super Admin 전용)</span>
            </div>
            <div style="font-size: 13px; color: #475569; font-weight: 500; margin-top: 6px; line-height: 1.5;">
                본 메뉴는 시스템 최고 관리자(<b>Super Admin: newprim</b>) 계정으로 로그인한 경우에만 조회 및 관리가 가능합니다.<br>
                일반 관리자(Admin) 계정은 시스템 관리 메뉴 및 계정 등록 메뉴에 접근할 수 없습니다.
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # 1. Hero Section (Cisco 테마 표준 배너)
    st.markdown("""
    <div style="background: #ffffff; border: 1.2px solid #e2e8f0; border-left: 4.5px solid #005073; border-radius: 8px; padding: 16px 22px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0, 45, 66, 0.04);">
        <div style="font-size: 20px; font-weight: 800; color: #002d42; display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
            <span>👤</span>
            <span>시스템 관리자 계정 관리</span>
            <span style="font-size: 12px; background: #e0f2fe; color: #0284c7; border: 1px solid #bae6fd; padding: 2px 8px; border-radius: 4px; font-weight: 700;">Super Admin 전용</span>
        </div>
        <div style="font-size: 13px; color: #475569; font-weight: 500; line-height: 1.6;">
            대시보드에 로그인할 수 있는 관리자 계정을 신규 등록하고 관리합니다.<br>
            • <b>newprim (Super Admin)</b>: 모든 메뉴 및 시스템 관리, 계정 등록/관리 등 전체 권한 보유<br>
            • <b>신규 등록 계정 (Admin)</b>: 작업 원장, 통계 분석, 실적 관리 등 일반 업무 권한 보유 (시스템 관리 메뉴는 자동 숨김 처리)
        </div>
        <div style="margin-top: 10px; padding-top: 8px; border-top: 1px dashed #e2e8f0; font-size: 12.5px; color: #334155; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <span style="background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; padding: 2px 7px; border-radius: 4px; font-weight: 700; font-size: 11px;">🛡️ 단방향 암호화 적용</span>
            <span><b>PBKDF2-HMAC-SHA256 (100,000회 솔트 해시)</b>로 저장되어 복호화 키가 존재하지 않으며, DB가 유출되어도 원래 비밀번호 복원이 원천 불가능합니다.</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_create, col_list = st.columns([1.0, 1.25], gap="large")

    # 2. 신규 계정 등록 폼 (표준 st.form 활용 -> 깔끔한 네모 카드 박스)
    with col_create:
        st.markdown("<h4 style='color: #002d42; font-weight: 800; font-size: 16px; margin-bottom: 10px;'>➕ 신규 관리자(Admin) 계정 등록</h4>", unsafe_allow_html=True)
        
        with st.form("form_register_admin", clear_on_submit=True):
            new_u = st.text_input("아이디 (Username)", placeholder="예: admin_kim")
            new_p = st.text_input("비밀번호 (Password)", type="password", placeholder="최소 4자 이상")
            new_name = st.text_input("담당자 성명", placeholder="예: 김철수 대리")
            new_note = st.text_input("비고 (소속/용도)", placeholder="예: 기술1팀 운영 관리자")
            
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            submit_btn = st.form_submit_button("➕ 신규 관리자 계정 등록", type="primary", use_container_width=True)
            
            if submit_btn:
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

    # 3. 등록된 관리자 계정 목록 (맨 앞 네모 체크박스 기반 계정 관리)
    with col_list:
        st.markdown("<h4 style='color: #002d42; font-weight: 800; font-size: 16px; margin-bottom: 10px;'>👥 등록된 관리자 계정 목록</h4>", unsafe_allow_html=True)
        
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

                border_left_color = "#f59e0b" if is_super else "#0284c7"
                role_badge = (
                    '<span style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: #ffffff; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 800;">👑 Super Admin</span>'
                    if is_super else
                    '<span style="background: #0284c7; color: #ffffff; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 800;">🛡️ Admin</span>'
                )

                with st.container():
                    # 상단 줄: 맨 앞 체크박스 + 계정 정보 카드
                    c_chk, c_info = st.columns([0.08, 0.92], vertical_alignment="center")
                    
                    with c_chk:
                        is_selected = st.checkbox("선택", key=f"chk_manage_{un}", label_visibility="collapsed")
                    
                    with c_info:
                        st.markdown(f"""
                        <div style="background: #ffffff; border: 1.2px solid #e2e8f0; border-left: 4px solid {border_left_color}; border-radius: 8px; padding: 12px 16px; box-shadow: 0 1px 3px rgba(0,45,66,0.03);">
                            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    {role_badge}
                                    <span style="font-weight: 800; color: #002d42; font-size: 14.5px;">{un}</span>
                                    <span style="color: #475569; font-weight: 600; font-size: 13px;">({name or '성명 미등록'})</span>
                                </div>
                                <div style="font-size: 11.5px; color: #94a3b8;">
                                    등록: {dt}
                                </div>
                            </div>
                            {f'<div style="margin-top: 5px; font-size: 12px; color: #64748b;">📌 비고: {note}</div>' if note else ''}
                        </div>
                        """, unsafe_allow_html=True)

                    # ✅ 맨 앞 네모박스(체크박스) 체크 시 하단에 계정 제어 패널 펼침
                    if is_selected:
                        st.markdown(f"""
                        <div style="background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 6px; padding: 10px 14px; margin: 4px 0 10px 28px;">
                            <div style="font-size: 12.5px; font-weight: 800; color: #005073; margin-bottom: 6px;">
                                ⚙️ [{un}] 계정 제어 패널
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        ctrl_col1, ctrl_col2 = st.columns([1.2, 0.8], gap="medium")
                        with ctrl_col1:
                            new_pwd_input = st.text_input("새 비밀번호 입력", type="password", key=f"edit_pwd_{un}", placeholder="변경할 새 비밀번호")
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
                        with ctrl_col2:
                            if is_super:
                                st.markdown("<div style='background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; margin-top: 22px; color: #64748b; font-size: 11.5px; font-weight: 600; text-align: center;'>🔒 Super Admin 본인 계정은<br>삭제할 수 없습니다.</div>", unsafe_allow_html=True)
                            else:
                                st.markdown("<div style='height: 22px;'></div>", unsafe_allow_html=True)
                                if st.button(f"🗑️ [{un}] 계정 삭제", key=f"btn_del_{un}", type="secondary", use_container_width=True):
                                    succ, msg = AuthManager.delete_account(un)
                                    if succ:
                                        st.toast(msg, icon="✅")
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)
                    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
