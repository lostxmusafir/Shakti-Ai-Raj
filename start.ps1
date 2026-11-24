# Universal AI Analyst - PowerShell Launcher
$ErrorActionPreference = 'Continue'
Set-Location -Path $PSScriptRoot

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "    Starting Universal AI Analyst Platform" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python
$pyCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pyCmd = 'python'
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pyCmd = 'py'
} else {
    Write-Host "[ERROR] Python was not found on PATH. Install Python 3.11+ and try again." -ForegroundColor Red
    pause
    exit 1
}

# 2. Check npm
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] npm was not found on PATH. Install Node.js 18+ and try again." -ForegroundColor Red
    pause
    exit 1
}

# 3. Free development ports
Write-Host "[1/4] Checking and freeing development ports (8000, 3000)..." -ForegroundColor Yellow
Get-NetTCPConnection -LocalPort 8000, 3000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $pId = $_.OwningProcess
    Write-Host "  - Terminating process holding port $($_.LocalPort) [PID $pId]..." -ForegroundColor Gray
    Stop-Process -Id $pId -Force -ErrorAction SilentlyContinue
}

# 4. Backend venv
$venvPy = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "[2/4] Setting up backend virtual environment..." -ForegroundColor Yellow
    & $pyCmd -m venv (Join-Path $PSScriptRoot "backend\.venv")
    Write-Host "  - Installing backend dependencies..." -ForegroundColor Gray
    & $venvPy -m pip install -r (Join-Path $PSScriptRoot "backend\requirements.txt")
} else {
    Write-Host "[2/4] Backend environment ready." -ForegroundColor Green
}

# 5. Frontend node_modules
$nodeModules = Join-Path $PSScriptRoot "frontend\node_modules"
if (-not (Test-Path $nodeModules)) {
    Write-Host "[3/4] Installing frontend dependencies..." -ForegroundColor Yellow
    Push-Location (Join-Path $PSScriptRoot "frontend")
    npm ci
    Pop-Location
} else {
    Write-Host "[3/4] Frontend environment ready." -ForegroundColor Green
}

# 6. Launch services in separate windows
Write-Host "[4/4] Launching services..." -ForegroundColor Green
Write-Host ""
Write-Host "  * Backend:  http://localhost:8000 (API docs: http://localhost:8000/docs)" -ForegroundColor Cyan
Write-Host "  * Frontend: http://localhost:3000" -ForegroundColor Cyan
Write-Host ""

$backendDir = Join-Path $PSScriptRoot "backend"
$frontendDir = Join-Path $PSScriptRoot "frontend"

Start-Process -FilePath "cmd.exe" -ArgumentList "/k", ".venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" -WorkingDirectory $backendDir
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "npm run dev" -WorkingDirectory $frontendDir

Write-Host "Both services have been started in separate terminal windows." -ForegroundColor Green
Write-Host "To stop them at any time, run stop.bat or close their windows." -ForegroundColor Gray
