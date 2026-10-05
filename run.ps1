# Inventory Intelligence - Run Script for Windows PowerShell
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$VenvDir = Join-Path $BackendDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$NodeModulesDir = Join-Path $FrontendDir "node_modules"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Inventory Intelligence - Starting Services" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $VenvPython)) {
    Write-Host "Error: Backend virtual environment missing." -ForegroundColor Red
    Write-Host "Please run .\setup.ps1 first." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $NodeModulesDir)) {
    Write-Host "Error: Frontend node_modules missing." -ForegroundColor Red
    Write-Host "Please run .\setup.ps1 first." -ForegroundColor Yellow
    exit 1
}

Write-Host "Launching Backend (FastAPI on http://127.0.0.1:8000)..." -ForegroundColor Green
$BackendBlock = "& { Set-Location '$BackendDir'; & '$VenvPython' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 }"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $BackendBlock

Write-Host "Launching Frontend (Next.js on http://localhost:3000)..." -ForegroundColor Green
$FrontendBlock = "& { Set-Location '$FrontendDir'; npm run dev }"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $FrontendBlock

Write-Host "Waiting for services to initialize..." -ForegroundColor Gray

$BackendReady = $false
$FrontendReady = $false

for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    if (-not $BackendReady) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($resp.StatusCode -eq 200) { $BackendReady = $true }
        } catch {}
    }
    if (-not $FrontendReady) {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($resp.StatusCode -eq 200) { $FrontendReady = $true }
        } catch {}
    }
    if ($BackendReady -and $FrontendReady) { break }
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Services Status" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
if ($BackendReady) {
    Write-Host "  Backend:  http://127.0.0.1:8000 [ONLINE]" -ForegroundColor Green
} else {
    Write-Host "  Backend:  http://127.0.0.1:8000 [STARTING/CHECK LOGS]" -ForegroundColor Yellow
}

if ($FrontendReady) {
    Write-Host "  Frontend: http://localhost:3000 [ONLINE]" -ForegroundColor Green
} else {
    Write-Host "  Frontend: http://localhost:3000 [STARTING/CHECK LOGS]" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "To stop services, run .\stop.ps1 or close the service windows." -ForegroundColor Gray
Write-Host ""
