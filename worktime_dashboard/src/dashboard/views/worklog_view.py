import io
from datetime import datetime
import pandas as pd
import streamlit as st
from ..common.ui_helpers import strip_tz
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
        st.download_button(
            label="📥 업무 현황 엑셀(.xlsx) 리포트 다운로드",
            data=excel_data,
            file_name=f"업무현황_상세리포트_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    display_cols = [
        "start_time", "end_time", "status", "log_type", "worker_name", "worker_team",
        "client_name", "task_description", "estimated_hours", "actual_hours", "is_night_work", "is_weekend_work"
    ]
    available_display_cols = [c for c in display_cols if c in df.columns]
    disp_df_out = strip_tz(df[available_display_cols].copy())
    if "start_time" in disp_df_out.columns:
        disp_df_out = disp_df_out.sort_values(by="start_time", ascending=False)
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
    sel_worklog_event = st.dataframe(
        disp_renamed,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="worklog_view_table_selector"
    )
    if sel_worklog_event and hasattr(sel_worklog_event, "selection") and sel_worklog_event.selection.rows:
        w_row_idx = sel_worklog_event.selection.rows[0]
        if w_row_idx < len(disp_df_out):
            row_dict = disp_df_out.iloc[w_row_idx].to_dict()
            w_key = f"worklog_{row_dict.get('id', w_row_idx)}_{w_row_idx}"
            if st.session_state.get("_last_dialog_worklog_row") != w_key:
                st.session_state["_last_dialog_worklog_row"] = w_key
                show_single_task_dialog(row_dict)
    else:
        st.session_state["_last_dialog_worklog_row"] = None
    return
