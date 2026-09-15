import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from ...analytics.stats_service import StatsService

def render_duration_view(df: pd.DataFrame):
    """⏱️ 예정 소요시간 대비 실제 시간 편차 분석 화면"""
    st.subheader("⏱️ 예정 소요시간 대비 실제 시간 편차 분석")
    completed_df = df[(df["status"] == "COMPLETED") & (df["estimated_minutes"] > 0)].copy()
    
    if not completed_df.empty:
        completed_df["diff_minutes"] = completed_df["actual_minutes"] - completed_df["estimated_minutes"]
        completed_df["diff_hours"] = (completed_df["diff_minutes"] / 60.0).round(1)
        completed_df["overdue_status"] = completed_df["diff_minutes"].apply(
            lambda x: "초과 소요" if x > 0 else ("단축 완료" if x < 0 else "정시 완료")
        )
        
        col_t5_1, col_t5_2 = st.columns([3, 2])
        with col_t5_1:
            fig_scatter = px.scatter(
                completed_df,
                x="estimated_hours",
                y="actual_hours",
                color="overdue_status",
                hover_data=["worker_name", "client_name", "task_description"],
                color_discrete_map={"초과 소요": "#E53935", "단축 완료": "#43A047", "정시 완료": "#1E88E5"},
                labels={"estimated_hours": "예정 시간(h)", "actual_hours": "실제 완료 시간(h)"},
                title="예정 시간 vs 실제 완료 시간 비교 산점도"
            )
            max_val = max(completed_df["estimated_hours"].max(), completed_df["actual_hours"].max()) + 1
            fig_scatter.add_trace(go.Scatter(
                x=[0, max_val], y=[0, max_val],
                mode='lines',
                line=dict(dash='dash', color='gray'),
                name='예정=실제 기준선'
            ))
            fig_scatter.update_layout(height=380)
            st.plotly_chart(fig_scatter, use_container_width=True)

        with col_t5_2:
            type_summary = StatsService.get_type_summary(df)
            fig_type = px.bar(
                type_summary,
                x="log_type",
                y="total_hours",
                color="log_type",
                labels={"log_type": "작업 구분", "total_hours": "시간(h)"},
                title="작업 유형별(정기점검, OS업그레이드 등) 투입 시간"
            )
            fig_type.update_layout(height=380, showlegend=False)
            st.plotly_chart(fig_type, use_container_width=True)


