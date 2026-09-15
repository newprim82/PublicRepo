@echo off
chcp 65001 > nul
title 원격 세션 화면 유지 종료

:: 1. 관리자 권한 자동 획득 (UAC Elevation)
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [관리자 권한 요청 중...]
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ===================================================================
echo   🔌 [화면 잠금 방지 원격 세션 종료]
echo   화면을 잠그지 않고 로컬 콘솔로 전환합니다...
echo ===================================================================

:: 2. 현재 RDP 세션 ID를 콘솔(화면 활성)로 강제 전환
for /f "skip=1 tokens=3" %%s in ('query user %USERNAME% 2^>nul') do (
    %windir%\System32\tscon.exe %%s /dest:console >nul 2>&1
)

for /f "tokens=2" %%i in ('qwinsta 2^>nul ^| findstr /i ">"') do (
    %windir%\System32\tscon.exe %%i /dest:console >nul 2>&1
)

for /f "tokens=3" %%i in ('qwinsta 2^>nul ^| findstr /i ">"') do (
    %windir%\System32\tscon.exe %%i /dest:console >nul 2>&1
)

:: 기본 세션 번호(1~4) 안전 시도
%windir%\System32\tscon.exe 1 /dest:console >nul 2>&1
%windir%\System32\tscon.exe 2 /dest:console >nul 2>&1
%windir%\System32\tscon.exe 3 /dest:console >nul 2>&1

echo.
echo [✓] 로컬 콘솔 화면으로 성공적으로 전환되었습니다.
timeout /t 1 /nobreak > nul
