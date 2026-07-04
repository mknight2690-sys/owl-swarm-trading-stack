# Foreground 1m tick notifier — keep this terminal open in Cursor (visible badge above prompt).
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$PidFile = Join-Path $Root "state\token_launch_loop.pid"
$IntervalSec = 60
$Sentinel = "AGENT_LOOP_TICK_TOKEN_LAUNCH"
$DueFlag = Join-Path $Root ".cursor\TOKEN_LAUNCH_DUE"

$Prompt = @"
TOKEN LAUNCH 1m tick LIVE — tokenomics, deploy, promote, outreach. Never wait on user.
Read .cursor/skills/token-launch-agent/SKILL.md and execute the full checklist.
Run: python scripts/token_launch_tick.py then python scripts/token_launch_execute.py
When zalalena due: open https://faucet.zalalena.com/base, complete captcha, Request 0.015 ETH to deployer wallet.
Live mode: TOKEN_FACTORY_DRY_RUN=false TOKEN_FACTORY_LIVE=true. Auto-fund testnet gas.
Gmail via Wholesaling sibling OAuth. Never commit .env, keys, or state/.
Mark done: delete .cursor/TOKEN_LAUNCH_DUE and update state/last_cursor_token_launch.txt.
"@.Replace("`r`n", " ").Trim()

$bgPid = 0
if (Test-Path $PidFile) {
    try { $bgPid = [int](Get-Content $PidFile -ErrorAction Stop | Select-Object -First 1) } catch { }
    if ($bgPid -gt 0 -and $bgPid -ne $PID) {
        Stop-Process -Id $bgPid -Force -ErrorAction SilentlyContinue
    }
}
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "token_launch_loop_worker\.ps1" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

New-Item -ItemType Directory -Force -Path (Split-Path $PidFile) | Out-Null
$PID | Out-File $PidFile -Encoding ascii -NoNewline
New-Item -ItemType Directory -Force -Path (Split-Path $DueFlag) | Out-Null
$ts = [int][double]::Parse((Get-Date -UFormat %s))
Set-Content -Path $DueFlag -Value "due_since=$ts`ninterval_sec=$IntervalSec`nsource=notify_loop`n" -Encoding utf8

Write-Host "=== Token Launch LIVE tick notifier (FOREGROUND) ==="
Write-Host "pid=$PID interval=${IntervalSec}s sentinel=$Sentinel"
Write-Host "Keep this terminal open. Cursor watches for tick lines."
Write-Host "Stop: Ctrl+C or scripts\start_token_launch_loop.ps1 -Stop"
Write-Host ""

$json = (@{ prompt = $Prompt } | ConvertTo-Json -Compress)
Write-Output "$Sentinel $json"

while ($true) {
    Start-Sleep -Seconds $IntervalSec
    $json = (@{ prompt = $Prompt } | ConvertTo-Json -Compress)
    Write-Output "$Sentinel $json"
}
