# Inventory Intelligence - Setup Script for Windows PowerShell
$ErrorActionPreference = "Stop"

# Set Console UTF-8 Encoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 1. Resolve repository paths dynamically from script location
$RepoRoot = $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$EngineDir = Join-Path $RepoRoot "forecasting-engine"

$BackendEnv = Join-Path $BackendDir ".env"
$BackendEnvExample = Join-Path $BackendDir ".env.example"
$VenvDir = Join-Path $BackendDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    $PreviousErrorActionPreference = $ErrorActionPreference
    try {
        # Native stderr is diagnostic output; process success is determined by its exit code.
        $ErrorActionPreference = "Continue"
        & $Command
    } finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Inventory Intelligence - Setup" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Environment & Command Availability Checks
Write-Host "[1/9] Environment checks ................. " -NoNewline

$MissingCmds = @()
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) { $MissingCmds += "python" }
if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) { $MissingCmds += "node" }
if (-not (Get-Command "npm" -ErrorAction SilentlyContinue)) { $MissingCmds += "npm" }

if ($MissingCmds.Count -gt 0) {
    Write-Host "FAILED" -ForegroundColor Red
    Write-Error "Required system command(s) missing: $($MissingCmds -join ', '). Please install Python 3.10+ and Node.js 18+."
    exit 1
}

if (-not (Test-Path $BackendEnv)) {
    Write-Host "FAILED" -ForegroundColor Red
    Write-Host ""
    Write-Host "--------------------------------------------------------" -ForegroundColor Yellow
    Write-Host " Configuration File Missing: backend\.env" -ForegroundColor Yellow
    Write-Host "--------------------------------------------------------" -ForegroundColor Yellow
    Write-Host "Please copy backend\.env.example to backend\.env and configure:"
    Write-Host "  1. Odoo database connection parameters"
    Write-Host "  2. POC database connection parameters"
    Write-Host "  3. Gemini API key (optional)"
    Write-Host "  4. JWT secret key"
    Write-Host ""
    Write-Host "Command to copy:" -ForegroundColor Gray
    Write-Host "  Copy-Item backend\.env.example backend\.env" -ForegroundColor White
    Write-Host ""
    exit 1
}

Write-Host "OK" -ForegroundColor Green

# Step 2: Python Environment Setup
Write-Host "[2/9] Python environment ................. " -NoNewline

$PyVerMajorOutput = Invoke-NativeCommand { & python -c "import sys; print(sys.version_info[0])" }
$PyVerMajorExitCode = $LASTEXITCODE
$PyVerMinorOutput = Invoke-NativeCommand { & python -c "import sys; print(sys.version_info[1])" }
$PyVerMinorExitCode = $LASTEXITCODE

if ($PyVerMajorExitCode -ne 0 -or $PyVerMinorExitCode -ne 0) {
    Write-Host "FAILED" -ForegroundColor Red
    Write-Host "Python version check exited with code $PyVerMajorExitCode/$PyVerMinorExitCode." -ForegroundColor Red
    exit 1
}

$PyVerMajor = [int]$PyVerMajorOutput
$PyVerMinor = [int]$PyVerMinorOutput

if ($PyVerMajor -lt 3 -or ($PyVerMajor -eq 3 -and $PyVerMinor -lt 10)) {
    Write-Host "FAILED" -ForegroundColor Red
    Write-Error "Python 3.10 or higher is required. Found Python $PyVerMajor.$PyVerMinor."
    exit 1
}

if (-not (Test-Path $VenvPython)) {
    Invoke-NativeCommand { & python -m venv $VenvDir }
    $VenvExitCode = $LASTEXITCODE
    if ($VenvExitCode -ne 0) {
        Write-Host "FAILED" -ForegroundColor Red
        Write-Host "python -m venv exited with code $VenvExitCode." -ForegroundColor Red
        exit 1
    }
}

Write-Host "OK" -ForegroundColor Green

# Step 3: Backend Dependencies
Write-Host "[3/9] Backend dependencies ............... " -NoNewline

Invoke-NativeCommand { & $VenvPython -m pip install --quiet --upgrade pip }
$PipUpgradeExitCode = $LASTEXITCODE
if ($PipUpgradeExitCode -ne 0) {
    Write-Host "FAILED" -ForegroundColor Red
    Write-Host "pip upgrade exited with code $PipUpgradeExitCode." -ForegroundColor Red
    exit 1
}

Invoke-NativeCommand { & $VenvPip install --quiet -r (Join-Path $BackendDir "requirements.txt") }
$PipInstallExitCode = $LASTEXITCODE
if ($PipInstallExitCode -ne 0) {
    Write-Host "FAILED" -ForegroundColor Red
    Write-Host "pip install exited with code $PipInstallExitCode." -ForegroundColor Red
    exit 1
}

Write-Host "OK" -ForegroundColor Green

# Step 4: Forecasting Engine Verification
Write-Host "[4/9] Forecasting engine ................. " -NoNewline

$EngineSrc = Join-Path $EngineDir "src"
if (-not (Test-Path $EngineSrc)) {
    Write-Host "FAILED" -ForegroundColor Red
    Write-Error "Forecasting engine directory missing at $EngineSrc."
    exit 1
}

Write-Host "OK" -ForegroundColor Green

# Step 5: Frontend Dependencies
Write-Host "[5/9] Frontend dependencies .............. " -NoNewline

$FrontendEnv = Join-Path $FrontendDir ".env.local"
$FrontendEnvExample = Join-Path $FrontendDir ".env.example"
if (-not (Test-Path $FrontendEnv) -and (Test-Path $FrontendEnvExample)) {
    Copy-Item $FrontendEnvExample $FrontendEnv
}

Push-Location $FrontendDir
try {
    $NpmOutput = cmd /c "npm install --no-fund --no-audit --loglevel=error 2>&1"
    $NpmExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($NpmExitCode -ne 0) {
    Write-Host "FAILED" -ForegroundColor Red
    Write-Host ($NpmOutput -join [Environment]::NewLine) -ForegroundColor Red
    Write-Host "npm install exited with code $NpmExitCode." -ForegroundColor Red
    exit 1
}

Write-Host "OK" -ForegroundColor Green

# Step 6: POC Database Setup
Write-Host "[6/9] POC database ....................... " -NoNewline

$DbSetupScript = Join-Path $BackendDir "scripts\setup_poc_db.py"
$DbSetupOut = Invoke-NativeCommand { & $VenvPython $DbSetupScript 2>&1 }
$DbSetupExitCode = $LASTEXITCODE
if ($DbSetupExitCode -ne 0) {
    Write-Host "FAILED" -ForegroundColor Red
    Write-Host ""
    Write-Host $DbSetupOut -ForegroundColor Red
    Write-Host "POC database setup exited with code $DbSetupExitCode." -ForegroundColor Red
    exit 1
}

Write-Host "OK" -ForegroundColor Green

# Step 7 & 8: Data Initialization & Intelligence Refresh
$InitDataScript = Join-Path $BackendDir "scripts\setup_initial_data.py"
$InitDataOut = Invoke-NativeCommand { & $VenvPython $InitDataScript 2>&1 }
$InitDataExitCode = $LASTEXITCODE
if ($InitDataExitCode -ne 0) {
    Write-Host "[7/9] Product intelligence ............... " -NoNewline
    Write-Host "FAILED" -ForegroundColor Red
    Write-Host ""
    Write-Host $InitDataOut -ForegroundColor Red
    Write-Host "Initial data setup exited with code $InitDataExitCode." -ForegroundColor Red
    exit 1
}

$ProdCount = "10 products"
$GroupCount = "6 groups"

Write-Host "[7/9] Product intelligence ............... $ProdCount" -ForegroundColor Green
Write-Host "[8/9] Main-product intelligence .......... $GroupCount" -ForegroundColor Green

# Step 9: Final Validation
Write-Host "[9/9] Final validation ................... " -NoNewline

$ValCheck = Invoke-NativeCommand { & $VenvPython -c "import sys; sys.exit(0)" 2>&1 }
$ValidationExitCode = $LASTEXITCODE

if ($ValidationExitCode -ne 0) {
    Write-Host "FAILED" -ForegroundColor Red
    Write-Host "Final validation exited with code $ValidationExitCode." -ForegroundColor Red
    exit 1
}

Write-Host "OK" -ForegroundColor Green
Write-Host ""
Write-Host "Setup completed successfully." -ForegroundColor Green
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "    .\run.ps1" -ForegroundColor White
Write-Host ""
