import streamlit as st
from src.auth.auth_manager import AuthManager

@st.fragment
def render_login_page():
    """🔐 기술본부 관리자 로그인 전용 페이지"""
    st.markdown("""
    <style>
        .login-card {
            background: linear-gradient(135deg, #002233 0%, #003a55 50%, #004d71 100%);
            border: 1px solid #005f8a;
            border-radius: 12px;
            padding: 32px 36px 24px 36px;
            box-shadow: 0 8px 32px rgba(0, 34, 51, 0.35);
            text-align: center;
            margin-bottom: 20px;
        }
        .login-title {
            font-size: 22px;
            font-weight: 800;
            color: #ffffff;
            letter-spacing: -0.4px;
            margin-top: 8px;
            text-shadow: 0 1px 3px rgba(0,0,0,0.5);
        }
        .login-sub {
            font-size: 12.5px;
            color: #94a3b8;
            margin-top: 6px;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    col_l, col_center, col_r = st.columns([1, 1.4, 1])
    with col_center:
        st.markdown("""
        <div class="login-card">
            <div style="font-size: 36px;">🔐</div>
            <div class="login-title">기술본부 관리자 로그인</div>
            <div class="login-sub">시스템 설정 및 작업 원장 관리를 위한 관리자 인증 (24시간 세션 유지)</div>
        </div>
        """, unsafe_allow_html=True)

        if AuthManager.is_authenticated():
            current_admin = AuthManager.get_current_user() or "newprim"
            st.success(f"✅ 현재 **{current_admin}** 계정으로 로그인되어 있습니다.")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.button(
                    "🏠 대시보드로 이동",
                    use_container_width=True,
                    type="primary",
                    on_click=lambda: st.session_state.update({"current_page": "🏠 실시간 분석 대시보드"})
                )
            with col_b2:
                if st.button("🚪 로그아웃", use_container_width=True):
                    AuthManager.logout()
                    st.toast("👋 로그아웃되었습니다.", icon="ℹ️")
                    st.rerun()
            return

        with st.form("admin_login_form", clear_on_submit=False):
            u_input = st.text_input("👤 관리자 아이디 (ID)", placeholder="아이디 입력", key="login_id_field")
            p_input = st.text_input("🔑 비밀번호 (Password)", type="password", placeholder="비밀번호 입력", key="login_pw_field")
            
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            submit = st.form_submit_button("🔓 로그인 (Login)", type="primary", use_container_width=True)
            
            if submit:
                if AuthManager.login(u_input, p_input):
                    st.toast("🎉 로그인 성공! 모든 관리자 권한이 활성화되었습니다.", icon="✅")
                    st.session_state["current_page"] = "🏠 실시간 분석 대시보드"
                    st.rerun()
                else:
                    st.error("⚠️ 아이디 또는 비밀번호가 올바르지 않습니다.")


