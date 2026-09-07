import io
from datetime import datetime
import pandas as pd
import streamlit as st
from ..common.ui_helpers import strip_tz

@st.fragment
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
    clean_df = strip_tz(df)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        clean_df.to_excel(writer, index=False, sheet_name="지원시간통계")
    excel_data = output.getvalue()
    
    btn_col, _ = st.columns([2.0, 5.0])
    with btn_col:
        st.download_button(
            label="📥 엑셀(.xlsx) 원장 다운로드",
            data=excel_data,
            file_name=f"작업지원시간_통계_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    display_cols = [
        "start_time", "status", "log_type", "worker_name", "worker_team",
        "client_name", "task_description", "estimated_hours", "actual_hours", "is_night_work", "is_weekend_work"
    ]
    available_display_cols = [c for c in display_cols if c in df.columns]
    disp_df_out = strip_tz(df[available_display_cols].copy())
    if "status" in disp_df_out.columns:
        disp_df_out["status"] = disp_df_out["status"].map({"PENDING": "진행 중", "COMPLETED": "완료"}).fillna(disp_df_out["status"])
    
    st.dataframe(
        disp_df_out.rename(columns={
            "start_time": "시작 보고시각",
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
        }),
        use_container_width=True,
        hide_index=True
    )
    return
