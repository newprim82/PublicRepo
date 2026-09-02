@echo off
chcp 65001 > nul
title 팀 지원 시간 대시보드 [설정 및 실행]

echo ===================================================================
echo   🚀 [최초 설정 및 대시보드 실행]
echo   기존 프로세스를 정리하고 필수 패키지를 설치한 뒤 대시보드를 실행합니다...
echo ===================================================================
cd /d "%~dp0"

echo.
echo [1/2] 기존에 실행 중인 대시보드 프로세스를 정리합니다...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8501" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
taskkill /F /IM streamlit.exe >nul 2>&1
timeout /t 1 /nobreak > nul

echo.
echo [2/3] 필수 패키지 점검...
pip install -r requirements.txt

echo.
echo [3/3] 파이썬 및 Streamlit 로컬 임시 캐시를 정리합니다...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" >nul 2>&1
del /s /q *.pyc >nul 2>&1

echo.
echo -------------------------------------------------------------------
echo   팀 지원 시간 & 업무량 분석 대시보드 구동 중...
echo -------------------------------------------------------------------
python -m streamlit run src\dashboard\app.py
pause
