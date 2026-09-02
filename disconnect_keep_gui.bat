@echo off
chcp 65001 > nul
title 원격 세션 화면 유지 종료
echo ===================================================================
echo   🔌 [화면 잠금 방지 원격 세션 종료]
echo   화면을 잠그지 않고 로컬 콘솔로 넘겨 자동 수집이 계속 작동하게 합니다...
echo ===================================================================
timeout /t 1 /nobreak > nul

for /f tokens=2 %%i in ('qwinsta ^| findstr /i >') do (
    tscon %%i /dest:console
)

for /f tokens=3 %%i in ('qwinsta ^| findstr /i >') do (
    tscon %%i /dest:console
)

echo.
echo [✓] 로컬 콘솔로 전환되었습니다. 원격 창이 닫힙니다.
timeout /t 2 /nobreak > nul
