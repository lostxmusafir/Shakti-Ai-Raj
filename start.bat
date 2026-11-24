@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ===================================================
echo     Starting Universal AI Analyst Platform
echo ===================================================
echo.

:: 1. Check Python
set "PYTHON_CMD="
where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
) else (
    where py >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_CMD=py"
    )
)

if "%PYTHON_CMD%"=="" (
    echo [ERROR] Python was not found on PATH. Install Python 3.11+ and try again.
    pause
    exit /b 1
)

:: 2. Check npm
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] npm was not found on PATH. Install Node.js 18+ and try again.
    pause
    exit /b 1
)

:: 3. Free ports 8000 and 3000 from any stale background processes
echo [1/4] Checking and freeing development ports...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo   - Freeing port 8000 [PID %%a]...
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    echo   - Freeing port 3000 [PID %%a]...
    taskkill /F /PID %%a >nul 2>&1
)

:: 4. Backend environment & dependencies
if not exist "backend\.venv\Scripts\python.exe" (
    echo [2/4] Setting up backend virtual environment...
    %PYTHON_CMD% -m venv backend\.venv
    if not exist "backend\.venv\Scripts\python.exe" (
        echo   - Fallback: creating venv without pip...
        %PYTHON_CMD% -m venv --without-pip backend\.venv
        if not exist "backend\.venv\Scripts\python.exe" goto :failed
    )
    echo   - Installing backend dependencies...
    if exist "backend\.venv\Scripts\pip.exe" (
        "backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
    ) else (
        %PYTHON_CMD% -m pip --python "backend\.venv\Scripts\python.exe" install -r backend\requirements.txt
    )
    if %errorlevel% neq 0 goto :failed
) else (
    if /I "%~1"=="--install" (
        echo [2/4] Updating backend dependencies [--install specified]...
        "backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
        if %errorlevel% neq 0 goto :failed
    ) else (
        echo [2/4] Backend environment ready.
    )
)

:: 5. Frontend environment & dependencies
if not exist "frontend\node_modules" (
    echo [3/4] Installing frontend dependencies...
    pushd frontend
    call npm ci
    if %errorlevel% neq 0 (
        call npm install
        if %errorlevel% neq 0 (
            popd
            goto :failed
        )
    )
    popd
) else (
    echo [3/4] Frontend environment ready.
)

:: 6. Launch services
echo [4/4] Launching services...
echo.
echo   * Backend:  http://localhost:8000  (API docs: http://localhost:8000/docs)
echo   * Frontend: http://localhost:3000
echo.

start "Universal AI Analyst Backend" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

start "Universal AI Analyst Frontend" /D "%~dp0frontend" cmd /k "npm run dev"

echo Both services have been started in separate terminal windows.
echo To stop them at any time, run stop.bat or close their windows.
echo.
exit /b 0

:failed
echo.
echo [ERROR] Setup failed. Review the output messages above.
pause
exit /b 1
