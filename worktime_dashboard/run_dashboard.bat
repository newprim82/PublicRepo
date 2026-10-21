@echo off
chcp 65001 > nul
title WorkLens 대시보드 실행
echo ===================================================================
echo   [대시보드 시작] WorkLens 스마트 업무 분석 웹 대시보드 실행 중...
echo ===================================================================
cd /d "%~dp0"
python -m streamlit run src\dashboard\app.py
pause
