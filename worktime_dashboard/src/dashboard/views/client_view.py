import pandas as pd
import streamlit as st
import plotly.express as px
from ...analytics.stats_service import StatsService

def render_client_view(df: pd.DataFrame):
    """🏢 고객사별 지원 시간 및 공수 비중 화면"""
    st.subheader("🏢 고객사별 지원 시간 및 공수 비중")
    client_summary = StatsService.get_client_summary(df)
    
    if not client_summary.empty:
        col_t4_1, col_t4_2 = st.columns([1, 1])
        with col_t4_1:
            fig_client_pie = px.pie(
                client_summary,
                names="client_name",
                values="total_hours",
                hole=0.45,
                title="고객사별 투입 공수(시간) 점유율",
                labels={"client_name": "고객사", "total_hours": "시간"}
            )
            fig_client_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_client_pie.update_layout(height=400)
            st.plotly_chart(fig_client_pie, use_container_width=True)

        with col_t4_2:
            fig_client_bar = px.bar(
                client_summary,
                x="total_hours",
                y="client_name",
                orientation='h',
                labels={"total_hours": "총 투입시간(h)", "client_name": "고객사"},
                title="고객사별 투입 시간(h) 순위",
                color="total_hours",
                color_continuous_scale="Viridis"
            )
            fig_client_bar.update_layout(height=400, yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_client_bar, use_container_width=True)

