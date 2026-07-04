# BaaS Arcade — 1m Cursor agent loop (foreground = visible terminal above prompt).
param(
    [switch]$Stop,
    [switch]$Status,
    [switch]$NoImmediateTick,
    [switch]$Foreground
)

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

function Get-BaasLoopProcesses {
    @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object {
        ($_.CommandLine -match "start_baas_arcade_loop\.ps1" -or
         $_.CommandLine -match "baas_arcade_notify_loop\.ps1" -or
         $_.CommandLine -match "baas_arcade_loop_worker\.ps1") -and
        $_.CommandLine -notmatch "\-Stop\b"
    })
}

function Stop-BaasLoop {
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
    foreach ($p in Get-BaasLoopProcesses) {
        if ($p.ProcessId -eq $PID) { continue }
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        $stopped++
    }
    return $stopped
}

if ($Stop) {
    $n = Stop-BaasLoop
    if (Test-Path $DueFlag) { Remove-Item $DueFlag -Force -ErrorAction SilentlyContinue }
    Write-Host "Stopped $n BaaS arcade loop process(es)."
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
        $procs = @(Get-BaasLoopProcesses)
        $alive = $procs.Count -gt 0
        if ($alive) { $loopPid = $procs[0].ProcessId }
    }
    if ($alive) {
        $mode = "background"
        try {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$loopPid" -ErrorAction SilentlyContinue).CommandLine
            if ($cmd -match "baas_arcade_notify_loop\.ps1") { $mode = "foreground (Cursor terminal)" }
        } catch { }
        Write-Host "BaaS arcade Cursor loop: RUNNING pid=$loopPid mode=$mode (every 1m, sentinel $Sentinel)"
    } else {
        Write-Host "BaaS arcade Cursor loop: NOT RUNNING"
    }
    if (Test-Path $DueFlag) { Write-Host "BAAS_ARCADE_DUE flag: SET" }
    exit 0
}

Stop-BaasLoop | Out-Null
Start-Sleep -Seconds 1
New-Item -ItemType Directory -Force -Path (Split-Path $PidFile) | Out-Null

if ($Foreground) {
    & (Join-Path $PSScriptRoot "baas_arcade_notify_loop.ps1")
    exit 0
}

$worker = Join-Path $PSScriptRoot "baas_arcade_loop_worker.ps1"
$proc = Start-Process -FilePath powershell.exe -WindowStyle Hidden -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $worker,
    "-Prompt", $Prompt, "-IntervalSec", $IntervalSec
) -WorkingDirectory $Root -PassThru

$proc.Id | Out-File $PidFile -Encoding ascii -NoNewline
New-Item -ItemType Directory -Force -Path (Split-Path $DueFlag) | Out-Null
$ts = [int][double]::Parse((Get-Date -UFormat %s))
Set-Content -Path $DueFlag -Value "due_since=$ts`ninterval_sec=$IntervalSec`nsource=baas_loop`n" -Encoding utf8

if (-not $NoImmediateTick) {
    $json = (@{ prompt = $Prompt } | ConvertTo-Json -Compress)
    Write-Output "$Sentinel $json"
}

Write-Host "BaaS background loop started pid=$($proc.Id)"
Write-Host "Visible terminal: powershell -File scripts\start_baas_arcade_loop.ps1 -Foreground"
