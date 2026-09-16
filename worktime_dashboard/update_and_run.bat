@echo off
chcp 65001 > nul
title 팀 지원 시간 대시보드 [업데이트 및 실행]

echo ===================================================================
echo   🔄 [최신 버전 업데이트 및 실행]
echo   기존 프로세스를 종료하고 GitHub에서 최신 코드를 받아 실행합니다...
echo ===================================================================
cd /d "%~dp0"

echo.
echo [1/4] 기존에 실행 중인 대시보드 프로세스를 정리합니다...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8501" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
taskkill /F /IM streamlit.exe >nul 2>&1
timeout /t 1 /nobreak > nul

echo.
echo [2/4] GitHub에서 최신 소스코드를 강제 동기화하여 내려받습니다...
git fetch origin main
git reset --hard origin/main

if exist "%~dp0worktime_dashboard\requirements.txt" (
    cd /d "%~dp0worktime_dashboard"
) else (
    cd /d "%~dp0"
)
pip install -r requirements.txt

echo.
echo [3/4] 파이썬 네이티브 캐시 가속을 적용하여 대시보드를 구동합니다...

echo.
echo -------------------------------------------------------------------
echo   [4/4] 팀 지원 시간 & 업무량 분석 대시보드 구동 중...
echo -------------------------------------------------------------------
python -m streamlit run src\dashboard\app.py
pause
