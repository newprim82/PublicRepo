import pandas as pd
import streamlit as st
from ...services.team_service import TeamService, DEFAULT_TEAMS, UNASSIGNED_TEAM
from ..common.ui_helpers import get_all_teams_safe

def render_team_management_page(all_workers_list, team_mappings):
    """[⚙️ 팀원 소속 및 직급 관리] 전용 관리 페이지 (신규 팀 생성 + 소속팀 + 직급 완벽 지원)"""
    # 🎨 Cisco ACI Deep Cyan-Navy 전용 프리미엄 테마 주입
    st.markdown("""
    <style>
        /* 🏢 관리 페이지 전용 Cisco ACI 테마 스타일링 */

        /* 1. Primary 액션 버튼 (새 팀 생성, 소속팀 및 직급 즉시 저장, 표 수정 내용 전체 저장) -> Cisco ACI Deep Blue */
        [data-testid="stMain"] div.stButton > button[kind="primary"] {
            background-color: #005073 !important;
            border: 1px solid #003852 !important;
            border-radius: 6px !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            font-size: 13.5px !important;
            padding: 6px 14px !important;
            box-shadow: 0 2px 5px rgba(0, 80, 115, 0.25) !important;
            transition: all 0.2s ease !important;
        }
        [data-testid="stMain"] div.stButton > button[kind="primary"] * {
            color: #ffffff !important;
            font-weight: 700 !important;
        }
        [data-testid="stMain"] div.stButton > button[kind="primary"]:hover {
            background-color: #003852 !important;
            border-color: #002233 !important;
            box-shadow: 0 3px 8px rgba(0, 80, 115, 0.4) !important;
        }

        /* 2. Secondary 버튼 (팀 삭제, ❌ 해제, 전체 일괄 해제) -> 소프트 레드 경고 버튼 */
        [data-testid="stMain"] div.stButton > button[kind="secondary"],
        [data-testid="stMain"] div.stButton > button:not([kind="primary"]) {
            background-color: #fee2e2 !important;
            border: 1.5px solid #fca5a5 !important;
            border-radius: 6px !important;
            color: #dc2626 !important;
            font-weight: 700 !important;
            font-size: 13px !important;
            padding: 5px 12px !important;
            transition: all 0.2s ease !important;
        }
        [data-testid="stMain"] div.stButton > button[kind="secondary"] *,
        [data-testid="stMain"] div.stButton > button:not([kind="primary"]) * {
            color: #dc2626 !important;
            font-weight: 700 !important;
        }
        [data-testid="stMain"] div.stButton > button[kind="secondary"]:hover,
        [data-testid="stMain"] div.stButton > button:not([kind="primary"]):hover {
            background-color: #fecaca !important;
            border-color: #f87171 !important;
            color: #b91c1c !important;
        }
        [data-testid="stMain"] div.stButton > button[kind="secondary"]:hover *,
        [data-testid="stMain"] div.stButton > button:not([kind="primary"]):hover * {
            color: #b91c1c !important;
        }

        /* 3. 텍스트 입력창 (st.text_input) -> 화이트 필드 & 딥 시안 포커스 */
        [data-testid="stMain"] [data-testid="stTextInput"] input {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
            padding: 6px 12px !important;
        }
        [data-testid="stMain"] [data-testid="stTextInput"] input:focus {
            border-color: #00b4d8 !important;
            box-shadow: 0 0 0 2px rgba(0, 180, 216, 0.2) !important;
        }
        [data-testid="stMain"] [data-testid="stTextInput"] input::placeholder {
            color: #94a3b8 !important;
        }

        /* 4. 셀렉트박스 (st.selectbox) -> 화이트 필드 & 네이비 텍스트 */
        [data-testid="stMain"] [data-baseweb="select"] {
            background-color: #ffffff !important;
            border-radius: 6px !important;
        }
        [data-testid="stMain"] [data-baseweb="select"] > div {
            background-color: #ffffff !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 6px !important;
        }
        [data-testid="stMain"] [data-baseweb="select"] * {
            color: #0f172a !important;
            font-weight: 600 !important;
        }
        [data-testid="stMain"] [data-baseweb="select"] svg {
            fill: #005073 !important;
        }

        /* 5. 코드 태그 (`코드`) -> ACI 소프트 시안 뱃지 */
        [data-testid="stMain"] code {
            background-color: #e0f2fe !important;
            color: #0369a1 !important;
            font-weight: 700 !important;
            border: 1px solid #bae6fd !important;
            border-radius: 4px !important;
            padding: 2px 6px !important;
        }

        /* 6. 아코디언 (st.expander) -> ACI 화이트 카드 & 좌측 딥 시안 라인 */
        [data-testid="stMain"] [data-testid="stExpander"] {
            background-color: #ffffff !important;
            border: 1.5px solid #cbd5e1 !important;
            border-left: 5px solid #005073 !important;
            border-radius: 8px !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04) !important;
            margin-bottom: 12px !important;
        }
        [data-testid="stMain"] [data-testid="stExpander"] details {
            background-color: #ffffff !important;
            border-radius: 8px !important;
        }
        [data-testid="stMain"] [data-testid="stExpander"] summary {
            background-color: #f8fafc !important;
            border-bottom: 1px solid #e2e8f0 !important;
            padding: 10px 16px !important;
            border-radius: 6px 6px 0 0 !important;
        }
        [data-testid="stMain"] [data-testid="stExpander"] summary span,
        [data-testid="stMain"] [data-testid="stExpander"] summary p {
            color: #005073 !important;
            font-weight: 800 !important;
            font-size: 14px !important;
        }
        [data-testid="stMain"] [data-testid="stExpander"] summary:hover {
            background-color: #f1f5f9 !important;
        }
        [data-testid="stMain"] [data-testid="stExpander"] summary svg {
            fill: #005073 !important;
        }
    </style>
    """, unsafe_allow_html=True)
    st.header("⚙️ 팀원 소속 및 직급 관리 (팀 생성 & 배정)")
    st.markdown("부서/팀(`기술본부`, `기술 1팀`, `기술 2팀`, `기술 3팀`, `PI팀` 및 **직접 생성한 신규 팀**)별로 팀원의 **소속팀과 직급(`사원`, `대리`, `과장`, `수석`)**을 배정하고 자유롭게 생성/수정/해제할 수 있습니다.")
    st.divider()

    all_teams = get_all_teams_safe()
    COMPANY_TITLES = ["사원", "대리", "과장", "수석"]
    members_info = TeamService.get_team_members_info()

    # 0. 신규 팀 생성 및 팀 관리 섹션
    st.markdown("### 🏢 0. 신규 팀 생성 및 팀 목록 관리")
    st.caption("기본 팀(`기술본부`, `기술 1팀`, `기술 2팀`, `기술 3팀`, `PI팀`) 외에 필요한 **새로운 팀을 자유롭게 생성하거나 삭제**할 수 있습니다.")
    
    col_t_create, col_t_del = st.columns([1.2, 0.8])
    with col_t_create:
        c_in1, c_in2 = st.columns([2.5, 1.2])
        with c_in1:
            new_team_input = st.text_input("새 팀 이름 입력", placeholder="예: 인프라팀, 보안팀, 솔루션사업팀 등", label_visibility="collapsed", key="input_new_custom_team")
        with c_in2:
            if st.button("➕ 새 팀 생성", use_container_width=True, type="primary"):
                t_str = new_team_input.strip() if new_team_input else ""
                if t_str:
                    if t_str in all_teams:
                        st.warning(f"이미 존재하는 팀 이름입니다: {t_str}")
                    else:
                        TeamService.add_custom_team(t_str)
                        st.toast(f"🎉 [{t_str}] 팀이 성공적으로 생성되었습니다!", icon="✅")
                        st.rerun()
                else:
                    st.warning("생성할 팀 이름을 입력해주세요.")

    with col_t_del:
        custom_teams = [t for t in all_teams if t not in DEFAULT_TEAMS]
        if custom_teams:
            c_d1, c_d2 = st.columns([2.0, 1.2])
            with c_d1:
                del_pick = st.selectbox("삭제할 커스텀 팀", options=custom_teams, label_visibility="collapsed", key="del_team_pick_sb")
            with c_d2:
                if st.button("🗑️ 팀 삭제", use_container_width=True):
                    TeamService.delete_custom_team(del_pick)
                    st.toast(f"🗑️ [{del_pick}] 팀이 삭제되었습니다.", icon="✅")
                    st.rerun()
        else:
            st.caption("💡 사용자가 직접 추가한 커스텀 팀이 있을 때 여기서 삭제할 수 있습니다.")

    st.divider()

    col_assign, col_status = st.columns([1.1, 0.9])

    # 1. 팀원별 소속팀 & 직급 개별 간편 설정
    with col_assign:
        st.markdown("### 📥 1. 팀원별 소속팀 & 직급 빠른 설정")
        st.caption("팀원을 선택하고 소속팀과 직급을 지정한 뒤 저장하시면 **DB와 작업 원장에 즉시 동기화**됩니다.")
        
        if all_workers_list:
            pick_worker = st.selectbox("1️⃣ 담당자 선택:", options=all_workers_list, key="pick_worker_manage")
            
            cur_worker_team = members_info.get(pick_worker, {}).get("team", "기술 1팀")
            cur_worker_title = members_info.get(pick_worker, {}).get("title", "")
            
            team_idx = all_teams.index(cur_worker_team) if cur_worker_team in all_teams else 0
            
            c_sel1, c_sel2 = st.columns(2)
            with c_sel1:
                sel_team = st.selectbox("2️⃣ 소속 팀 지정:", options=all_teams + [UNASSIGNED_TEAM], index=team_idx if team_idx < len(all_teams) else 0, key="sel_team_manage")
            with c_sel2:
                avail_titles = COMPANY_TITLES + ["(미지정)"]
                title_idx = COMPANY_TITLES.index(cur_worker_title) if cur_worker_title in COMPANY_TITLES else (len(avail_titles) - 1)
                
                sel_title = st.selectbox("3️⃣ 직급 선택 (4대 직급):", options=avail_titles, index=title_idx, key="sel_title_manage")

            final_title = "" if sel_title == "(미지정)" else sel_title.strip()

            if st.button("💾 소속팀 및 직급 즉시 저장 ⚡", use_container_width=True, type="primary"):
                TeamService.save_worker_info(pick_worker, sel_team, final_title)
                st.toast(f"🎉 [{pick_worker}] 님의 정보가 [{sel_team} | {final_title or '직급 미지정'}]으로 저장되었습니다!", icon="✅")
                st.rerun()

    # 2. 팀별 소속 인원 및 직급 현황
    with col_status:
        st.markdown("### 🏢 2. 팀별 소속 인원 & 직급 현황")
        
        # 전체 팀 현황 (동적 all_teams)
        for t_name in all_teams:
            m_list = [w for w in all_workers_list if members_info.get(w, {}).get("team", "") == t_name]
            with st.expander(f"🔹 {t_name} (총 {len(m_list)}명)", expanded=True if len(m_list) > 0 else False):
                if m_list:
                    st.caption("💡 각 팀원의 **직급을 선택하면 즉시 자동 저장⚡**되며, **[❌ 해제]**를 누르면 팀에서 제외됩니다.")
                    
                    # 2열 그리드로 팀원별 [이름 + 직급 셀렉트박스 + 개별 해제] 배치
                    grid_cols = st.columns(2)
                    for idx, name in enumerate(m_list):
                        cur_j_title = members_info.get(name, {}).get("title", "")
                        with grid_cols[idx % 2]:
                            c_name, c_title, c_del = st.columns([1.5, 2.0, 1.0])
                            with c_name:
                                st.markdown(f"<div style='padding-top:6px;'>👤 <b><code>{name}</code></b></div>", unsafe_allow_html=True)
                            with c_title:
                                title_opts = ["(미지정)", "사원", "대리", "과장", "수석"]
                                t_idx = title_opts.index(cur_j_title) if cur_j_title in title_opts else 0
                                new_t = st.selectbox(
                                    "직급",
                                    options=title_opts,
                                    index=t_idx,
                                    label_visibility="collapsed",
                                    key=f"team_direct_title_{t_name}_{name}"
                                )
                                final_new_t = "" if new_t == "(미지정)" else new_t
                                if final_new_t != cur_j_title:
                                    TeamService.update_worker_title(name, final_new_t)
                                    st.toast(f"⚡ [{name}] 님의 직급이 [{final_new_t or '미지정'}]으로 자동 저장되었습니다!", icon="✅")
                                    st.rerun()
                            with c_del:
                                if st.button("❌ 해제", key=f"del_indiv_{t_name}_{name}"):
                                    TeamService.remove_worker_team(name)
                                    st.toast(f"🗑️ [{name}] 님의 {t_name} 소속이 해제되었습니다!", icon="✅")
                                    st.rerun()
                    
                    st.divider()
                    col_btn_clear, _ = st.columns([1, 1])
                    with col_btn_clear:
                        if st.button(f"🗑️ {t_name} 소속 전체 일괄 해제", key=f"clear_all_{t_name}"):
                            TeamService.clear_team_all_members(t_name)
                            st.warning(f"{t_name} 소속 팀원이 모두 해제되었습니다.")
                            st.rerun()
                else:
                    st.info(f"현재 {t_name}에 등록된 팀원이 없습니다.")

        # 미지정 현황
        unassigned_list = [w for w in all_workers_list if members_info.get(w, {}).get("team", UNASSIGNED_TEAM) == UNASSIGNED_TEAM]
        with st.expander(f"⚪ 소속 미지정 (총 {len(unassigned_list)}명)", expanded=True if len(unassigned_list) > 0 else False):
            if unassigned_list:
                items_str = [f"`{name}`" for name in unassigned_list]
                st.markdown("**미지정 인원:** " + ", ".join(items_str))
            else:
                st.success("모든 팀원이 소속 팀에 배정되어 있습니다.")

    st.divider()

    # 3. 테이블형 팀원 소속 & 직급 일괄 수정 / 삭제 에디터
    st.markdown("### 📋 3. 전체 팀원 소속 & 직급 일괄 수정 테이블")
    st.caption("아래 표에서 각 팀원의 **소속팀**과 **직급(사원/대리/과장/수석)**을 드롭다운으로 변경한 후 하단의 **[💾 표 수정 내용 전체 저장]** 버튼을 누르시면 한 번에 저장됩니다.")
    
    mapping_data = []
    for w in all_workers_list:
        w_info = members_info.get(w, {})
        cur_t = w_info.get("title", "")
        mapping_data.append({
            "담당자": w,
            "소속팀": w_info.get("team", UNASSIGNED_TEAM),
            "직급": cur_t if cur_t in COMPANY_TITLES else ""
        })
    mapping_df = pd.DataFrame(mapping_data)
    
    edited_df = st.data_editor(
        mapping_df,
        column_config={
            "담당자": st.column_config.TextColumn("담당자", disabled=True),
            "소속팀": st.column_config.SelectboxColumn(
                "소속팀",
                options=all_teams + [UNASSIGNED_TEAM],
                required=True
            ),
            "직급": st.column_config.SelectboxColumn(
                "직급",
                options=["사원", "대리", "과장", "수석", ""],
                required=False
            )
        },
        use_container_width=True,
        hide_index=True,
        key="team_data_editor_with_titles"
    )
    
    if st.button("💾 표 수정 내용 전체 저장", use_container_width=True, type="primary"):
        for _, row in edited_df.iterrows():
            w_name = row["담당자"]
            t_name = row["소속팀"]
            j_title = str(row["직급"]).strip() if pd.notna(row["직급"]) and str(row["직급"]).strip() != "None" else ""
            TeamService.save_worker_info(w_name, t_name, j_title)
        st.success("🎉 모든 팀원의 소속팀 및 직급 정보가 성공적으로 일괄 업데이트되었습니다!")
        st.rerun()


