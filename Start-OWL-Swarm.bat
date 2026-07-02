@echo off
REM OWL Swarm Desktop Launcher - keeps this window open while stack runs

title OWL Swarm Launcher
cd /d "%~dp0"

echo ============================================
echo   OWL Swarm - Starting...
echo   Kills ALL bots + dashboards, starts fresh single instance
echo   This window stays open while the swarm runs.
echo ============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch.ps1"
set EXITCODE=%ERRORLEVEL%

if %EXITCODE% NEQ 0 (
    echo.
    echo Launcher exited with error code %EXITCODE%.
    echo Check outputs\launcher.log and outputs\owl-stderr.log
    pause
    exit /b %EXITCODE%
)

echo.
echo Launcher ended unexpectedly. Press any key to close.
pause
