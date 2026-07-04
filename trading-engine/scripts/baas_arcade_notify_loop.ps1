# Foreground 1m tick notifier — keep this terminal open in Cursor.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$PidFile = Join-Path $Root "state\baas_arcade_loop.pid"
$IntervalSec = 60
$Sentinel = "AGENT_LOOP_TICK_BAAS_ARCADE"
$DueFlag = Join-Path $Root ".cursor\BAAS_ARCADE_DUE"

$Prompt = @"
BAAS ARCADE 1m tick — market, sell, optimize bot-as-a-service offerings.
Read .cursor/skills/baas-arcade/SKILL.md and execute the full checklist.
Run: python scripts/baas_agent_tick.py
Free/barter outreach only. Gmail via Wholesaling sibling OAuth or SMTP.
Mark done: delete .cursor/BAAS_ARCADE_DUE and update state/last_cursor_baas_arcade.txt.
"@.Replace("`r`n", " ").Trim()

$bgPid = 0
if (Test-Path $PidFile) {
    try { $bgPid = [int](Get-Content $PidFile -ErrorAction Stop | Select-Object -First 1) } catch { }
    if ($bgPid -gt 0 -and $bgPid -ne $PID) {
        Stop-Process -Id $bgPid -Force -ErrorAction SilentlyContinue
    }
}
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "baas_arcade_loop_worker\.ps1" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

New-Item -ItemType Directory -Force -Path (Split-Path $PidFile) | Out-Null
$PID | Out-File $PidFile -Encoding ascii -NoNewline
New-Item -ItemType Directory -Force -Path (Split-Path $DueFlag) | Out-Null
$ts = [int][double]::Parse((Get-Date -UFormat %s))
Set-Content -Path $DueFlag -Value "due_since=$ts`ninterval_sec=$IntervalSec`nsource=notify_loop`n" -Encoding utf8

Write-Host "=== BaaS Arcade tick notifier (FOREGROUND) ==="
Write-Host "pid=$PID interval=${IntervalSec}s sentinel=$Sentinel"
Write-Host "Keep this terminal open. Cursor watches for tick lines."
Write-Host "Stop: Ctrl+C or scripts\start_baas_arcade_loop.ps1 -Stop"
Write-Host ""

$json = (@{ prompt = $Prompt } | ConvertTo-Json -Compress)
Write-Output "$Sentinel $json"

while ($true) {
    Start-Sleep -Seconds $IntervalSec
    $json = (@{ prompt = $Prompt } | ConvertTo-Json -Compress)
    Write-Output "$Sentinel $json"
}
