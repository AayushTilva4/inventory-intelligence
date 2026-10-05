# Inventory Intelligence - Stop Script for Windows PowerShell
$ErrorActionPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "Stopping Inventory Intelligence services..." -ForegroundColor Yellow

# Terminate uvicorn backend processes
Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like "*uvicorn app.main:app*" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force 2>$null
}

# Terminate next dev frontend processes
Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like "*next*dev*" -or $_.CommandLine -like "*next-server*" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force 2>$null
}

Write-Host "Services stopped successfully." -ForegroundColor Green
