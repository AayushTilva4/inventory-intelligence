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

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Services Running" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Backend:  http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor White
Write-Host ""
Write-Host "To stop services, run .\stop.ps1 or close the service windows." -ForegroundColor Gray
Write-Host ""
