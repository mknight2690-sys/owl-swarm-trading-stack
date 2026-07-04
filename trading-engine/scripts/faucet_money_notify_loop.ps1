# Foreground 1m tick — real mainnet faucet money collector.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$PidFile = Join-Path $Root "state\faucet_money_loop.pid"
$IntervalSec = 60
$Sentinel = "AGENT_LOOP_TICK_FAUCET_MONEY"
$DueFlag = Join-Path $Root ".cursor\FAUCET_MONEY_DUE"

$Prompt = @"
FAUCET MONEY 1m tick — REAL mainnet only. Never wait on user.
Read .cursor/skills/faucet-money/SKILL.md and execute full checklist.
Run: py -3.12 scripts/faucet_money_repair.py then faucet_money_tick.py then faucet_money_execute.py then faucet_collection_agent.py tick
If active watch session: record browser steps with faucet_collection_agent watch step. Fix repair.json broken items first.
Register FaucetPay first, then Fire Faucet, Final AutoClaim, FreeBitco.in, CoinPayU, SatoshiHero, etc.
Browser: captcha claims when due. Confirm real money via mainnet explorer balances in tick.json.
Zalalena/testnet does NOT count as real money. Never commit .env, wallet_secrets.env, or state/.
Mark done: delete .cursor/FAUCET_MONEY_DUE and update state/last_cursor_faucet_money.txt.
"@.Replace("`r`n", " ").Trim()

$bgPid = 0
if (Test-Path $PidFile) {
    try { $bgPid = [int](Get-Content $PidFile -ErrorAction Stop | Select-Object -First 1) } catch { }
    if ($bgPid -gt 0 -and $bgPid -ne $PID) {
        Stop-Process -Id $bgPid -Force -ErrorAction SilentlyContinue
    }
}
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "faucet_money_loop_worker\.ps1" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

New-Item -ItemType Directory -Force -Path (Split-Path $PidFile) | Out-Null
$PID | Out-File $PidFile -Encoding ascii -NoNewline
New-Item -ItemType Directory -Force -Path (Split-Path $DueFlag) | Out-Null
$ts = [int][double]::Parse((Get-Date -UFormat %s))
Set-Content -Path $DueFlag -Value "due_since=$ts`ninterval_sec=$IntervalSec`nsource=notify_loop`n" -Encoding utf8

Write-Host "=== Faucet Money LIVE tick notifier (FOREGROUND) ==="
Write-Host "pid=$PID interval=${IntervalSec}s sentinel=$Sentinel"
Write-Host "REAL mainnet faucets only — testnet (Zalalena) excluded."
Write-Host "Stop: Ctrl+C or scripts\start_faucet_money_loop.ps1 -Stop"
Write-Host ""

$json = (@{ prompt = $Prompt } | ConvertTo-Json -Compress)
Write-Output "$Sentinel $json"

while ($true) {
    Start-Sleep -Seconds $IntervalSec
    $json = (@{ prompt = $Prompt } | ConvertTo-Json -Compress)
    Write-Output "$Sentinel $json"
}
