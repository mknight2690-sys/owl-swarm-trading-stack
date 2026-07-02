@echo off
REM OWL Swarm Desktop Stopper
REM Stops trading loop, monitor, dashboard server
REM Does NOT close your main Chrome browser

title Stopping OWL Swarm...
cd /d "%~dp0"

echo ============================================
echo   Stopping OWL Swarm...
echo   Kills ALL bots + dashboards on this computer
echo ============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"

echo.
echo Done. Press any key to close.
pause >nul
