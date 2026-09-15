@echo off
chcp 65001 > nul
cd /d "%~dp0worktime_dashboard"
python -m src.collector.kakao_auto_collector
pause
