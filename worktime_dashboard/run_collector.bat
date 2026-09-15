@echo off
chcp 65001 > nul
echo ===================================================
echo   카카오톡 PC 10분 주기 자동 수집기 실행 중...
echo ===================================================
cd /d "%~dp0"
python -m src.collector.kakao_auto_collector
pause
