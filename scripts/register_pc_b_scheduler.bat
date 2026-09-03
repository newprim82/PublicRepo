@echo off
chcp 65001 >nul
echo =======================================================
echo [WorkTime] PC B 매일 새벽 04:00 자동 업데이트 스케줄러 등록
echo =======================================================

set TASK_NAME=WorkTime_AutoUpdate_Collector
set SCRIPT_PATH=C:\Python\work-time-dashboard\scripts\update_and_restart_collector.bat

:: 기존 동일 작업 존재 시 삭제
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: 매일 새벽 04:00에 실행되는 스케줄 등록
schtasks /create /tn "%TASK_NAME%" /tr ""%SCRIPT_PATH%"" /sc daily /st 04:00 /ru "%USERNAME%" /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo =======================================================
    echo ✅ 작업 스케줄러 등록 성공!
    echo    - 작업 이름: %TASK_NAME%
    echo    - 실행 주기: 매일 새벽 04:00
    echo    - 실행 파일: %SCRIPT_PATH%
    echo =======================================================
) else (
    echo.
    echo ❌ 작업 스케줄러 등록 실패 (관리자 권한으로 다시 실행해주세요).
)

pause
