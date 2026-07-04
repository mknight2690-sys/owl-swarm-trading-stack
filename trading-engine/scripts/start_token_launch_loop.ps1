# Token Launch — 1m Cursor agent loop (foreground = visible terminal above prompt).
param(
    [switch]$Stop,
    [switch]$Status,
    [switch]$NoImmediateTick,
    [switch]$Foreground
)

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
When zalalena due (60m): claim https://faucet.zalalena.com/base — captcha + Request 0.015 ETH to deployer.
Live mode: TOKEN_FACTORY_DRY_RUN=false TOKEN_FACTORY_LIVE=true. Auto-fund testnet gas.
Gmail via Wholesaling sibling OAuth. Never commit .env, keys, or state/.
Mark done: delete .cursor/TOKEN_LAUNCH_DUE and update state/last_cursor_token_launch.txt.
"@.Replace("`r`n", " ").Trim()

function Get-TokenLaunchProcesses {
    @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object {
        ($_.CommandLine -match "start_token_launch_loop\.ps1" -or
         $_.CommandLine -match "token_launch_notify_loop\.ps1" -or
         $_.CommandLine -match "token_launch_loop_worker\.ps1") -and
        $_.CommandLine -notmatch "\-Stop\b"
    })
}

function Stop-TokenLaunchLoop {
    $stopped = 0
    if (Test-Path $PidFile) {
        $saved = 0
        try { $saved = [int](Get-Content $PidFile -ErrorAction Stop | Select-Object -First 1) } catch { }
        if ($saved -gt 0 -and $saved -ne $PID) {
            Stop-Process -Id $saved -Force -ErrorAction SilentlyContinue
            $stopped++
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    foreach ($p in Get-TokenLaunchProcesses) {
        if ($p.ProcessId -eq $PID) { continue }
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        $stopped++
    }
    return $stopped
}

if ($Stop) {
    $n = Stop-TokenLaunchLoop
    if (Test-Path $DueFlag) { Remove-Item $DueFlag -Force -ErrorAction SilentlyContinue }
    Write-Host "Stopped $n token launch loop process(es)."
    exit 0
}

if ($Status) {
    $alive = $false
    $loopPid = 0
    if (Test-Path $PidFile) {
        try { $loopPid = [int](Get-Content $PidFile -ErrorAction Stop | Select-Object -First 1) } catch { }
        if ($loopPid -gt 0) {
            $alive = $null -ne (Get-Process -Id $loopPid -ErrorAction SilentlyContinue)
        }
    }
    if (-not $alive) {
        $procs = @(Get-TokenLaunchProcesses)
        $alive = $procs.Count -gt 0
        if ($alive) { $loopPid = $procs[0].ProcessId }
    }
    if ($alive) {
        $mode = "background"
        try {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$loopPid" -ErrorAction SilentlyContinue).CommandLine
            if ($cmd -match "token_launch_notify_loop\.ps1") { $mode = "foreground (Cursor terminal)" }
        } catch { }
        Write-Host "Token launch Cursor loop: RUNNING pid=$loopPid mode=$mode (every 1m, sentinel $Sentinel)"
    } else {
        Write-Host "Token launch Cursor loop: NOT RUNNING"
    }
    if (Test-Path $DueFlag) { Write-Host "TOKEN_LAUNCH_DUE flag: SET" }
    exit 0
}

Stop-TokenLaunchLoop | Out-Null
Start-Sleep -Seconds 1
New-Item -ItemType Directory -Force -Path (Split-Path $PidFile) | Out-Null

if ($Foreground) {
    & (Join-Path $PSScriptRoot "token_launch_notify_loop.ps1")
    exit 0
}

$worker = Join-Path $PSScriptRoot "token_launch_loop_worker.ps1"
$proc = Start-Process -FilePath powershell.exe -WindowStyle Hidden -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $worker,
    "-Prompt", $Prompt, "-IntervalSec", $IntervalSec
) -WorkingDirectory $Root -PassThru

$proc.Id | Out-File $PidFile -Encoding ascii -NoNewline
New-Item -ItemType Directory -Force -Path (Split-Path $DueFlag) | Out-Null
$ts = [int][double]::Parse((Get-Date -UFormat %s))
Set-Content -Path $DueFlag -Value "due_since=$ts`ninterval_sec=$IntervalSec`nsource=token_launch_loop`n" -Encoding utf8

if (-not $NoImmediateTick) {
    $json = (@{ prompt = $Prompt } | ConvertTo-Json -Compress)
    Write-Output "$Sentinel $json"
}

Write-Host "Token launch background loop started pid=$($proc.Id)"
Write-Host "Visible terminal: powershell -File scripts\start_token_launch_loop.ps1 -Foreground"
