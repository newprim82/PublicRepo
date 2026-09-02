@echo off
chcp 65001 > nul
title 카카오톡 수집 단독 테스트
cd /d %~dp0
python test_kakao_capture.py
pause
