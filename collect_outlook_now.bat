@echo off
chcp 65001 > nul
cd /d "%~dp0worktime_dashboard"
python -m src.collector.outlook_auto_collector
pause
