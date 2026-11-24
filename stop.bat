@echo off
setlocal

cd /d "%~dp0"

echo ===================================================
echo     Stopping Universal AI Analyst Services
echo ===================================================
echo.

set "STOPPED=0"

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo   - Stopping backend service on port 8000 [PID %%a]...
    taskkill /F /PID %%a >nul 2>&1
    set "STOPPED=1"
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    echo   - Stopping frontend service on port 3000 [PID %%a]...
    taskkill /F /PID %%a >nul 2>&1
    set "STOPPED=1"
)

echo.
echo All Universal AI Analyst background servers stopped.
echo You can now safely close the server console windows.
echo.
pause
