@echo off
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH. Install Python 3.11+ and try again.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo npm was not found on PATH. Install Node.js 18+ and try again.
    pause
    exit /b 1
)

if not exist "backend\.venv\Scripts\python.exe" (
    echo Creating backend virtual environment...
    python -m venv --without-pip backend\.venv
    if errorlevel 1 goto :failed
)

echo Installing backend dependencies...
python -m pip --python "backend\.venv\Scripts\python.exe" install -r backend\requirements.txt
if errorlevel 1 goto :failed

if not exist "frontend\node_modules" (
    echo Installing frontend dependencies...
    pushd frontend
    call npm ci
    if errorlevel 1 (
        popd
        goto :failed
    )
    popd
)

echo Starting backend at http://localhost:8000 ...
start "Universal AI Analyst Backend" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

echo Starting frontend at http://localhost:3000 ...
start "Universal AI Analyst Frontend" /D "%~dp0frontend" cmd /k "npm run dev"

echo.
echo Both development servers are starting in separate windows.
exit /b 0

:failed
echo.
echo Dependency installation failed. Review the error above.
pause
exit /b 1
