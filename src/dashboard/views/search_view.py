import io
import re
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
from ...services.team_service import TeamService, UNASSIGNED_TEAM
from ..common.ui_helpers import strip_tz, format_raw_chat_display, is_same_team, get_all_teams_safe

def render_smart_search_tab(df_raw: pd.DataFrame, team_mappings: dict):
    """[🔍 전체 작업 스마트 검색] 다중 조건 실시간 통합 검색 탐색기 (독립 Fragment)"""
    # 🎨 스마트 검색 탭 전용 선명한 UI 스타일링 주입 (모든 버전의 Streamlit expander 및 input 완벽 호환)
    st.markdown("""
    <style>
        /* 1. 상세 검색 필터 expander 헤더 (본문 stMain 영역에만 한정 격리하여 사이드바 오염 방지) */
        div[data-testid="stMain"] [data-testid="stExpander"] details summary,
        div[data-testid="stMain"] [data-testid="stExpander"] summary,
        div[data-testid="stMain"] [data-testid="stExpanderSummary"],
        div[data-testid="stMain"] .streamlit-expanderHeader,
        div[data-testid="stMain"] div.streamlit-expanderHeader,
        div[data-testid="stMain"] details[data-testid="stExpander"] summary {
            background: linear-gradient(135deg, #002233 0%, #004d71 100%) !important;
            background-color: #002d42 !important;
            border: 1px solid #005f8a !important;
            border-radius: 8px !important;
            color: #ffffff !important;
            font-weight: 800 !important;
            padding: 10px 16px !important;
            box-shadow: 0 2px 6px rgba(0, 34, 51, 0.15) !important;
        }
        div[data-testid="stMain"] [data-testid="stExpander"] details summary *,
        div[data-testid="stMain"] [data-testid="stExpander"] summary *,
        div[data-testid="stMain"] [data-testid="stExpanderSummary"] *,
        div[data-testid="stMain"] .streamlit-expanderHeader *,
        div[data-testid="stMain"] details[data-testid="stExpander"] summary * {
            color: #ffffff !important;
            font-weight: 800 !important;
            font-size: 13.5px !important;
        }

        /* 2. 검색 입력 폼 (화이트 배경, 짙은 텍스트, 선명한 테두리) */
        div[data-testid="stMain"] div[data-testid="stExpander"] input,
        div[data-testid="stMain"] div[data-testid="stExpander"] select,
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="input"],
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="select"] > div,
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="base-input"],
        div[data-testid="stMain"] div[data-testid="stExpander"] div[data-testid="stDateInput"] input {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
            font-size: 13px !important;
        }
        div[data-testid="stMain"] div[data-testid="stExpander"] input::placeholder {
            color: #94a3b8 !important;
            font-weight: 500 !important;
        }
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="select"] span,
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="select"] div {
            color: #0f172a !important;
            font-weight: 600 !important;
        }
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="tag"] {
            background-color: #e0f2fe !important;
            color: #0369a1 !important;
            border: 1px solid #bae6fd !important;
            border-radius: 4px !important;
            font-weight: 700 !important;
        }
        div[data-testid="stMain"] div[data-testid="stExpander"] [data-baseweb="tag"] * {
            color: #0369a1 !important;
        }

        /* 3. 다운로드 버튼 (Cisco ACI Deep Blue + 볼드 화이트 글자 상시 노출) */
        div[data-testid="stMain"] .stDownloadButton button,
        div[data-testid="stMain"] [data-testid="stDownloadButton"] button,
        div[data-testid="stMain"] button[kind="primary"],
        div[data-testid="stMain"] button[data-testid="baseButton-secondary"]:has(p:contains("다운로드")),
        div[data-testid="stMain"] div.stDownloadButton > button {
            background: linear-gradient(135deg, #005073 0%, #003852 100%) !important;
            background-color: #005073 !important;
            color: #ffffff !important;
            border: 1px solid #002233 !important;
            font-weight: 800 !important;
            border-radius: 6px !important;
            padding: 8px 18px !important;
            box-shadow: 0 2px 5px rgba(0, 80, 115, 0.25) !important;
        }
        div[data-testid="stMain"] .stDownloadButton button *,
        div[data-testid="stMain"] [data-testid="stDownloadButton"] button *,
        div[data-testid="stMain"] div.stDownloadButton > button * {
            color: #ffffff !important;
            font-weight: 800 !important;
            font-size: 13px !important;
        }
        div[data-testid="stMain"] .stDownloadButton button:hover,
        div[data-testid="stMain"] [data-testid="stDownloadButton"] button:hover {
            background-color: #003852 !important;
            border-color: #001824 !important;
        }
        div[data-testid="stMain"] .stDownloadButton button:hover *,
        div[data-testid="stMain"] [data-testid="stDownloadButton"] button:hover * {
            color: #38bdf8 !important;
        }

    </style>
    """, unsafe_allow_html=True)

    st.markdown("### 🔍 전체 작업 통합 스마트 검색 & 다중 필터")
    st.caption("고객사명, 작업내용, 담당자, 소속팀, 야간/주말 여부 등 다중 조건을 조합하여 원하는 작업 이력을 0.1초 만에 실시간 검색합니다.")

    if df_raw.empty:
        st.info("검색할 작업 데이터가 존재하지 않습니다.")
        return

    search_df = df_raw.copy()
    
    # 누락될 수 있는 필수 컬럼 안전 기본값 초기화
    default_columns = {
        "id": 0,
        "worker_name": "",
        "worker_team": UNASSIGNED_TEAM,
        "worker_title": "",
        "client_name": "미지정",
        "task_description": "",
        "start_time": pd.NaT,
        "end_time": pd.NaT,
        "actual_hours": 0.0,
        "estimated_hours": 0.0,
        "status": "COMPLETED",
        "is_night_work": False,
        "is_weekend_work": False,
        "remarks": ""
    }
    for col_key, def_val in default_columns.items():
        if col_key not in search_df.columns:
            search_df[col_key] = def_val

    # 팀명 매핑 보정
    search_df["worker_team"] = search_df["worker_team"].fillna(search_df["worker_name"].map(team_mappings)).fillna(UNASSIGNED_TEAM)

    # 1. 다중 스마트 필터 컨트롤 패널 (라벨을 선명한 딥 네이비로 표출)
    with st.expander("🛠️ 상세 검색 필터 설정 (여기를 클릭하여 조건 접기/펼치기)", expanded=True):
        f_col1, f_col2, f_col3 = st.columns([2, 1.5, 1.5])
        with f_col1:
            st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 4px;">📝 통합 키워드 검색:</div>', unsafe_allow_html=True)
            keyword = st.text_input("통합 키워드 검색", placeholder="예: 정기점검, 장애처리, DR, 하나은행, BGF...", key="smart_kw", label_visibility="collapsed")
        with f_col2:
            st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 4px;">🏢 소속팀 필터:</div>', unsafe_allow_html=True)
            team_options = ["전체 팀"] + get_all_teams_safe() + [UNASSIGNED_TEAM]
            sel_team = st.selectbox("소속팀 필터:", options=team_options, index=0, key="smart_team", label_visibility="collapsed")
        with f_col3:
            st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 4px;">🏷️ 근무/상태 유형:</div>', unsafe_allow_html=True)
            type_options = ["전체", "⏳ 실시간 진행중", "✅ 작업 완료", "🌙 야간 근무", "🏖️ 주말 근무", "🚨 예정시간 초과"]
            sel_type = st.selectbox("근무/상태 유형:", options=type_options, index=0, key="smart_type", label_visibility="collapsed")

        f_col4, f_col5, f_col6 = st.columns([1.5, 1.5, 2])
        with f_col4:
            st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 4px;">🏢 고객사 다중 선택:</div>', unsafe_allow_html=True)
            all_clients = sorted([c for c in search_df["client_name"].dropna().unique() if str(c).strip()])
            sel_clients = st.multiselect("고객사 다중 선택:", options=all_clients, placeholder="고객사 선택 (전체)", key="smart_clients", label_visibility="collapsed")
        with f_col5:
            st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 4px;">👤 작업자 다중 선택:</div>', unsafe_allow_html=True)
            all_workers = sorted([w for w in search_df["worker_name"].dropna().unique() if str(w).strip()])
            sel_workers = st.multiselect("작업자 다중 선택:", options=all_workers, placeholder="작업자 선택 (전체)", key="smart_workers", label_visibility="collapsed")
        with f_col6:
            st.markdown('<div style="font-size: 13px; font-weight: 800; color: #002d42; margin-bottom: 4px;">📅 작업 기간 범위:</div>', unsafe_allow_html=True)
            min_date = search_df["start_time"].dt.date.min() if pd.notna(search_df["start_time"].min()) else datetime.now().date()
            max_date = search_df["start_time"].dt.date.max() if pd.notna(search_df["start_time"].max()) else datetime.now().date()
            date_range = st.date_input("작업 기간 범위:", value=(min_date, max_date), key="smart_date_range", label_visibility="collapsed")

    # 2. 필터링 로직 적용
    filtered_df = search_df.copy()

    # 키워드 검색
    if keyword and keyword.strip():
        kw = keyword.strip().lower()
        filtered_df = filtered_df[
            filtered_df["task_description"].fillna("").astype(str).str.lower().str.contains(kw, na=False) |
            filtered_df["client_name"].fillna("").astype(str).str.lower().str.contains(kw, na=False) |
            filtered_df["worker_name"].fillna("").astype(str).str.lower().str.contains(kw, na=False) |
            filtered_df["remarks"].fillna("").astype(str).str.lower().str.contains(kw, na=False)
        ]

    # 팀명 공백 무관 안전 비교 헬퍼
    def is_same_team(t1, t2):
        return str(t1).replace(" ", "").strip() == str(t2).replace(" ", "").strip()

    # 팀 필터
    if sel_team not in ["전체", "전체 팀"]:
        filtered_df = filtered_df[filtered_df["worker_team"].apply(lambda t: is_same_team(t, sel_team))]

    # 근무/상태 유형 필터
    if sel_type == "⏳ 실시간 진행중":
        filtered_df = filtered_df[filtered_df["status"] == "PENDING"]
    elif sel_type == "✅ 작업 완료":
        filtered_df = filtered_df[filtered_df["status"] == "COMPLETED"]
    elif sel_type == "🌙 야간 근무":
        filtered_df = filtered_df[filtered_df["is_night_work"] == True]
    elif sel_type == "🏖️ 주말 근무":
        filtered_df = filtered_df[filtered_df["is_weekend_work"] == True]
    elif sel_type == "🚨 예정시간 초과":
        filtered_df = filtered_df[
            (filtered_df["estimated_hours"] > 0) & 
            (filtered_df["actual_hours"] > filtered_df["estimated_hours"])
        ]

    # 고객사 필터
    if sel_clients:
        filtered_df = filtered_df[filtered_df["client_name"].isin(sel_clients)]

    # 작업자 필터
    if sel_workers:
        filtered_df = filtered_df[filtered_df["worker_name"].isin(sel_workers)]

    # 날짜 범위 필터
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        st_d, ed_d = date_range
        filtered_df = filtered_df[
            (filtered_df["start_time"].dt.date >= st_d) & 
            (filtered_df["start_time"].dt.date <= ed_d)
        ]

    filtered_df = filtered_df.sort_values("start_time", ascending=False)

    # 3. 실시간 결과 핵심 요약 카드 (메인 대시보드와 통일된 세련된 화이트 카드)
    res_cnt = len(filtered_df)
    res_hours = round(filtered_df["actual_hours"].sum(), 1)
    res_workers = filtered_df["worker_name"].nunique()
    res_clients = filtered_df["client_name"].nunique()

    res_cards_html = f"""<div style="display: flex; gap: 14px; margin-top: 14px; margin-bottom: 20px; flex-wrap: wrap;"><div style="flex: 1; min-width: 140px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #005073; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"><div style="font-size: 12.5px; font-weight: 700; color: #64748b; margin-bottom: 4px;">📋 검색된 작업</div><div style="font-size: 24px; font-weight: 900; color: #005073; letter-spacing: -0.5px;">{res_cnt:,}건</div></div><div style="flex: 1; min-width: 140px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #0284c7; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"><div style="font-size: 12.5px; font-weight: 700; color: #64748b; margin-bottom: 4px;">⏱️ 총 투입 공수</div><div style="font-size: 24px; font-weight: 900; color: #0284c7; letter-spacing: -0.5px;">{res_hours:,}시간</div></div><div style="flex: 1; min-width: 140px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #10b981; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"><div style="font-size: 12.5px; font-weight: 700; color: #64748b; margin-bottom: 4px;">👥 투입 인원</div><div style="font-size: 24px; font-weight: 900; color: #10b981; letter-spacing: -0.5px;">{res_workers}명</div></div><div style="flex: 1; min-width: 140px; background: #ffffff; border: 1px solid #e1e4e8; border-left: 4px solid #f59e0b; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"><div style="font-size: 12.5px; font-weight: 700; color: #64748b; margin-bottom: 4px;">🏢 관련 고객사</div><div style="font-size: 24px; font-weight: 900; color: #f59e0b; letter-spacing: -0.5px;">{res_clients}개사</div></div></div>"""
    st.markdown(res_cards_html, unsafe_allow_html=True)

    if filtered_df.empty:
        st.warning("🔍 설정하신 검색 조건에 부합하는 작업 내역이 없습니다. 다른 키워드나 조건으로 검색해 보세요.")
        return

    # 4. 결과 표출: 인터랙티브 테이블 뷰 및 엑셀(XLSX) 다운로드 단독 노출
    target_cols = [
        "worker_name", "worker_team", "worker_title", "client_name", 
        "task_description", "start_time", "end_time", "actual_hours", 
        "estimated_hours", "status", "is_night_work", "is_weekend_work", "remarks"
    ]
    available_cols = [c for c in target_cols if c in filtered_df.columns]
    export_df = filtered_df[available_cols].copy()
    if "start_time" in export_df.columns:
        export_df["start_time"] = export_df["start_time"].apply(lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else "")
    if "end_time" in export_df.columns:
        export_df["end_time"] = export_df["end_time"].apply(lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else "")
    display_df = export_df.rename(columns={
        "worker_name": "작업자",
        "worker_team": "소속팀",
        "worker_title": "직급",
        "client_name": "고객사",
        "task_description": "작업 내용",
        "start_time": "시작 시각",
        "end_time": "종료 시각",
        "actual_hours": "실제공수(h)",
        "estimated_hours": "예정공수(h)",
        "status": "상태",
        "is_night_work": "야간",
        "is_weekend_work": "주말",
        "remarks": "비고"
    })
    if "상태" in display_df.columns:
        display_df["상태"] = display_df["상태"].map({"PENDING": "진행 중", "COMPLETED": "완료"}).fillna(display_df["상태"])
    if "야간" in display_df.columns:
        display_df["야간"] = display_df["야간"].apply(lambda x: "Y" if x else "")
    if "주말" in display_df.columns:
        display_df["주말"] = display_df["주말"].apply(lambda x: "Y" if x else "")

    # 📊 엑셀(.xlsx) 파일 생성 및 다운로드 버튼
    import io
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        display_df.to_excel(writer, index=False, sheet_name="작업검색결과")
    excel_data = excel_buffer.getvalue()

    st.download_button(
        label="📥 검색 결과 엑셀(XLSX) 다운로드",
        data=excel_data,
        file_name=f"기술본부_작업검색결과_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_smart_search_xlsx"
    )

    st.dataframe(display_df, use_container_width=True, height=520)


@st.dialog("📧 Executive Summary 메일 발송", width="medium")


def render_search_view(df_raw: pd.DataFrame, team_mappings: dict):
    """🔍 전체 작업 스마트 검색 메인 뷰"""
    render_smart_search_tab(df_raw, team_mappings)
