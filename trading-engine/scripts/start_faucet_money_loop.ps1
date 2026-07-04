# Faucet Money — 1m Cursor agent loop (real mainnet faucets).
param(
    [switch]$Stop,
    [switch]$Status,
    [switch]$Foreground
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$PidFile = Join-Path $Root "state\faucet_money_loop.pid"
$Sentinel = "AGENT_LOOP_TICK_FAUCET_MONEY"
$DueFlag = Join-Path $Root ".cursor\FAUCET_MONEY_DUE"

function Get-FaucetMoneyProcesses {
    @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object {
        ($_.CommandLine -match "start_faucet_money_loop\.ps1" -or
         $_.CommandLine -match "faucet_money_notify_loop\.ps1") -and
        $_.CommandLine -notmatch "\-Stop\b"
    })
}

function Stop-FaucetMoneyLoop {
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
    foreach ($p in Get-FaucetMoneyProcesses) {
        if ($p.ProcessId -eq $PID) { continue }
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        $stopped++
    }
    return $stopped
}

if ($Stop) {
    $n = Stop-FaucetMoneyLoop
    if (Test-Path $DueFlag) { Remove-Item $DueFlag -Force -ErrorAction SilentlyContinue }
    Write-Host "Stopped $n faucet money loop process(es)."
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
        $procs = @(Get-FaucetMoneyProcesses)
        $alive = $procs.Count -gt 0
        if ($alive) { $loopPid = $procs[0].ProcessId }
    }
    if ($alive) {
        $mode = "background"
        try {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$loopPid" -ErrorAction SilentlyContinue).CommandLine
            if ($cmd -match "faucet_money_notify_loop\.ps1" -or $cmd -match "start_faucet_money_loop\.ps1") {
                $mode = "foreground (Cursor terminal)"
            }
        } catch { }
        Write-Host "Faucet money loop: RUNNING pid=$loopPid mode=$mode (every 1m, sentinel $Sentinel)"
    } else {
        Write-Host "Faucet money loop: NOT RUNNING"
    }
    if (Test-Path $DueFlag) { Write-Host "FAUCET_MONEY_DUE flag: SET" }
    exit 0
}

Stop-FaucetMoneyLoop | Out-Null
Start-Sleep -Seconds 1

if ($Foreground) {
    & (Join-Path $PSScriptRoot "faucet_money_notify_loop.ps1")
    exit 0
}

& (Join-Path $PSScriptRoot "faucet_money_notify_loop.ps1")
