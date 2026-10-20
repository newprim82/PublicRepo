import io
from datetime import datetime
import pandas as pd
import streamlit as st
from ..common.ui_helpers import strip_tz, extract_selected_row_idx, apply_weekend_table_styling
from ..common.dialogs import show_single_task_dialog
from ...services.excel_export_service import ExcelExportService

@st.cache_data(show_spinner=False)
def _get_cached_worklog_excel(df: pd.DataFrame) -> bytes:
    return ExcelExportService.generate_report(df, title_suffix="전체 작업 원장")

def render_worklog_view(df: pd.DataFrame):
    """📋 작업 지원 상세 기록 원장 & 엑셀 다운로드 화면"""
    st.subheader("📋 작업 지원 상세 기록 원장 & 엑셀 다운로드")
    
    # 🎨 Cisco ACI 다운로드 버튼 전용 스타일링 (글자 선명한 흰색 볼드 강제)
    st.markdown("""
    <style>
        div.stDownloadButton > button {
            background-color: #005073 !important;
            border: 1.5px solid #003852 !important;
            border-radius: 6px !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            font-size: 13.5px !important;
            padding: 6px 14px !important;
            box-shadow: 0 2px 5px rgba(0, 80, 115, 0.25) !important;
            transition: all 0.2s ease !important;
        }
        div.stDownloadButton > button *,
        div.stDownloadButton > button p,
        div.stDownloadButton > button span {
            color: #ffffff !important;
            font-weight: 700 !important;
            font-size: 13.5px !important;
        }
        div.stDownloadButton > button:hover {
            background-color: #003852 !important;
            border-color: #002233 !important;
            box-shadow: 0 3px 8px rgba(0, 80, 115, 0.4) !important;
        }
        div.stDownloadButton > button:hover * {
            color: #ffffff !important;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # openpyxl은 타임존(tz-aware) datetime을 지원하지 않으므로 strip_tz 적용
    excel_data = _get_cached_worklog_excel(df)
    
    btn_col, _ = st.columns([2.0, 5.0])
    with btn_col:
        from ...parser.reply_matcher import get_current_kst_time
        st.download_button(
            label="📥 업무 현황 엑셀(.xlsx) 리포트 다운로드",
            data=excel_data,
            file_name=f"업무현황_상세리포트_{get_current_kst_time().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    display_cols = [
        "start_time", "end_time", "status", "log_type", "worker_name", "worker_team",
        "client_name", "task_description", "estimated_hours", "actual_hours", "is_night_work", "is_weekend_work"
    ]
    full_sorted_df = strip_tz(df.copy())
    if "start_time" in full_sorted_df.columns:
        full_sorted_df = full_sorted_df.sort_values(by="start_time", ascending=False).reset_index(drop=True)

    available_display_cols = [c for c in display_cols if c in full_sorted_df.columns]
    disp_df_out = full_sorted_df[available_display_cols].copy()
    if "status" in disp_df_out.columns:
        disp_df_out["status"] = disp_df_out["status"].map({"PENDING": "진행 중", "COMPLETED": "완료"}).fillna(disp_df_out["status"])
    
    st.caption("💡 표에서 작업 행을 클릭하시면 해당 건의 카카오톡 시작/완료 보고 원본 대화 및 세부 정보 팝업이 표시됩니다.")
    disp_renamed = disp_df_out.rename(columns={
        "start_time": "시작 보고시각",
        "end_time": "완료 보고시각",
        "status": "상태",
        "log_type": "구분",
        "worker_name": "담당자",
        "worker_team": "소속팀",
        "client_name": "고객사",
        "task_description": "작업내용",
        "estimated_hours": "예정(h)",
        "actual_hours": "소요(h)",
        "is_night_work": "야간여부",
        "is_weekend_work": "주말여부"
    })
    @st.fragment
    def _render_worklog_table(disp_data, out_data):
        ver_key = "_tbl_ver_worklog_view"
        tbl_ver = st.session_state.get(ver_key, 0)
        sel_worklog_event = st.dataframe(
            disp_data,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode=["single-row", "single-cell"],
            key=f"worklog_view_table_selector_{tbl_ver}"
        )
        w_row_idx = extract_selected_row_idx(sel_worklog_event)
        if w_row_idx is not None and 0 <= w_row_idx < len(out_data):
            st.session_state[ver_key] = tbl_ver + 1
            row_dict = out_data.iloc[w_row_idx].to_dict()
            show_single_task_dialog(row_dict)

    styled_disp_renamed = apply_weekend_table_styling(disp_renamed, highlight_scope="full_row")
    _render_worklog_table(styled_disp_renamed, full_sorted_df)
    return
