@echo off
chcp 65001 >nul
title WorkTime Collector Auto-Update
echo =======================================================
echo [WorkTime] 카카오톡 수집기 자동 업데이트 및 재시작 (매일 04:00)
echo =======================================================

:: 프로젝트 루트 디렉토리(scripts 폴더의 상위)로 자동 이동 (PublicRepo 등 폴더명 자동 대응)
cd /d "%~dp0.."

echo [*] 1. 기존 실행 중인 수집기 프로세스 안전 종료 중...
taskkill /F /FI "WINDOWTITLE eq KakaoCollector*" /T >nul 2>&1
taskkill /F /IM python.exe /FI "MODULES eq win32gui*" >nul 2>&1

echo [*] 2. GitHub 최신 소스코드 강제 동기화 진행...
git fetch origin main
git reset --hard origin/main

echo [*] 3. 최신 코드로 카카오톡 자동 수집기 백그라운드 기동...
start "KakaoCollector" python run_collector.py

echo [OK] 자동 업데이트 및 수집기 재기동이 완료되었습니다!
timeout /t 5 >nul
