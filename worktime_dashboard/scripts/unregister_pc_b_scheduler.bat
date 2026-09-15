@echo off
chcp 65001 >nul
echo =======================================================
echo [WorkTime] PC B 자동 업데이트 작업 스케줄러 삭제
echo =======================================================

set TASK_NAME=WorkTime_AutoUpdate_Collector

schtasks /delete /tn "%TASK_NAME%" /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo =======================================================
    echo ✅ 자동 업데이트 스케줄러가 성공적으로 삭제되었습니다!
    echo    - 삭제된 작업: %TASK_NAME%
    echo    - 더 이상 새벽 4시에 강제 종료/재시작되지 않습니다.
    echo =======================================================
) else (
    echo.
    echo [-] 등록된 작업이 없거나 이미 삭제되었습니다.
)

pause
