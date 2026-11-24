# Universal AI Analyst - PowerShell Stop Script
$ErrorActionPreference = 'SilentlyContinue'

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "    Stopping Universal AI Analyst Services" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$found = $false
Get-NetTCPConnection -LocalPort 8000, 3000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $pId = $_.OwningProcess
    $proc = Get-Process -Id $pId -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "  - Stopping $($proc.ProcessName) on port $($_.LocalPort) [PID $pId]..." -ForegroundColor Yellow
        Stop-Process -Id $pId -Force -ErrorAction SilentlyContinue
        $found = $true
    }
}

if (-not $found) {
    Write-Host "No active services found listening on ports 8000 or 3000." -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "All Universal AI Analyst background servers stopped." -ForegroundColor Green
}
