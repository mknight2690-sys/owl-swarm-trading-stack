# AutoHedge on Blofin — verify trades, then run agent cycle
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
    .\.venv\Scripts\pip install -r requirements.txt
}

Write-Host "=== Verify Blofin trade API ===" -ForegroundColor Cyan
.\.venv\Scripts\python scripts\verify_blofin_trade.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n=== Verify agents (OpenRouter free model) ===" -ForegroundColor Cyan
.\.venv\Scripts\python scripts\verify_agents.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n=== Run AutoHedge (all instruments) ===" -ForegroundColor Cyan
.\.venv\Scripts\python scripts\run_blofin_autohedge.py @args
