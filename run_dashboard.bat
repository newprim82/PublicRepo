@echo off
chcp 65001 > nul
echo ========================================================
echo 🚀 팀 업무량 & 지원 시간 분석 대시보드 실행 (work-time-dashboard)
echo ========================================================
cd work-time-dashboard
streamlit run src/dashboard/app.py
pause
