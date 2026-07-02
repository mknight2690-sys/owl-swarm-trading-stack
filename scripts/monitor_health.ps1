# OWL Swarm health snapshot - called every 1 minute by monitor loop
$ErrorActionPreference = "SilentlyContinue"
$ProjectDir = "C:\Users\mknig\owl-swarm"
$LogFile = Join-Path $ProjectDir "outputs\monitor.log"
$DashboardURL = "http://127.0.0.1:7878/api/status"
. (Join-Path $ProjectDir "scripts\owl_common.ps1")

$python = "C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"

function Write-MonitorLog($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Add-Content -Path $LogFile -Value $line -ErrorAction SilentlyContinue
    return $line
}

$py = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*owl_llm_loop*' }

Clear-StaleOwlLock -ProjectDir $ProjectDir

# Single instance: kill duplicate owl_llm_loop (launcher owns orchestration when running)
if ($py -and @($py).Count -gt 1) {
    Repair-OwlStackDuplicates -ProjectDir $ProjectDir
    $py = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*owl_llm_loop*' } |
        Select-Object -First 1
}

$owlPid = if ($py) { $py.ProcessId } else { 0 }
$portPid = $null
try {
    $listener = netstat -ano | Select-String ":7878" | Select-String "LISTENING" | Select-Object -First 1
    if ($listener) {
        $parts = ($listener -split '\s+') | Where-Object { $_ -ne '' }
        $portPid = [int]$parts[-1]
    }
} catch { }

$dashOk = $false
$cycle = "?"
$equity = "?"
$running = "?"
$lastError = ""
$positions = "?"
$available = "?"

# Dashboard served by standalone server - port listener is enough when API slow
$dashServer = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*dashboard_server.py*' } |
    Select-Object -First 1

try {
    $resp = Invoke-WebRequest -Uri $DashboardURL -UseBasicParsing -TimeoutSec 25
    if ($resp.StatusCode -eq 200) {
        $dashOk = $true
        $j = $resp.Content | ConvertFrom-Json
        $cycle = $j.cycle
        $equity = [math]::Round([double]$j.equity, 4)
        $running = $j.running
        $lastError = $j.lastError
        $positions = @($j.positions).Count
        $available = [math]::Round([double]$j.available, 4)
    }
} catch {
    $lastError = $_.Exception.Message
}

# Fallback: read cached state when API is slow during LLM cycle
if (-not $dashOk -and $owlPid -and $portPid -eq $owlPid) {
    $stateFile = Join-Path $ProjectDir "outputs\owl-state.json"
    if (Test-Path $stateFile) {
        try {
            $st = Get-Content $stateFile -Raw | ConvertFrom-Json
            $cycle = $st.cycle
            $equity = [math]::Round([double]$st.equity, 4)
            $running = $true
            $lastError = if ($st.last_error) { $st.last_error } else { "api_slow_cached_ok" }
        } catch { }
    }
}

$status = if ($owlPid -and ($dashOk -or $dashServer)) { "HEALTHY" }
          elseif ($owlPid -and $portPid) { "DEGRADED" }
          elseif ($dashServer) { "DEGRADED" }
          else { "DOWN" }

$wsBridge = Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -like '*blofin_ws_bridge*' } |
    Select-Object -First 1
$wsPid = if ($wsBridge) { $wsBridge.ProcessId } else { 0 }

$wsCache = Join-Path $ProjectDir "outputs\ws-tickers.json"
$wsFresh = $false
if (Test-Path $wsCache) {
    $age = (Get-Date) - (Get-Item $wsCache).LastWriteTime
    $wsFresh = $age.TotalSeconds -lt 180
}

$summary = "status=$status py=$owlPid port=$portPid ws=$wsPid cycle=$cycle equity=`$$equity avail=`$$available pos=$positions running=$running ws_cache=$wsFresh"
if ($lastError) { $summary += " err=$lastError" }

$line = Write-MonitorLog $summary
Write-Output $line

if ($status -ne "HEALTHY") {
    $wakeCli = Join-Path $ProjectDir "scripts\cursor_wake_cli.py"
    if ((Test-Path $python) -and (Test-Path $wakeCli)) {
        & $python $wakeCli "monitor_$status" --detail $summary --source monitor_health --priority high 2>$null | Out-Null
    }
}

# Cycle log stall - also wake Cursor (scripts alone may be blocked on API)
$owlLog = Join-Path $ProjectDir "outputs\owl-llm.log"
if ($owlPid -and (Test-Path $owlLog)) {
    $logAge = ((Get-Date) - (Get-Item $owlLog).LastWriteTime).TotalSeconds
    if ($logAge -gt 600) {
        Write-MonitorLog "CYCLE_STALL log_idle=$([int]$logAge)s pid=$owlPid - stuck guard will unstick"
        $wakeCli = Join-Path $ProjectDir "scripts\cursor_wake_cli.py"
        if ((Test-Path $python) -and (Test-Path $wakeCli)) {
            & $python $wakeCli cycle_log_stall --detail "log_idle=$([int]$logAge)s pid=$owlPid" --priority critical 2>$null | Out-Null
        }
    }
}

# Python overseer: light tick with hard timeout (never block monitor >90s)
$overseerPy = Join-Path $ProjectDir "scripts\overseer_tick.py"
if ((Test-Path $python) -and (Test-Path $overseerPy)) {
    $job = Start-Job -ScriptBlock {
        param($py, $script)
        & $py $script 2>&1
    } -ArgumentList $python, $overseerPy
    $done = Wait-Job $job -Timeout 90
    if ($done) {
        $ov = (Receive-Job $job | Out-String).Trim()
        if ($ov) { Write-MonitorLog "OVERSEER $ov" }
    } else {
        Stop-Job $job -Force -ErrorAction SilentlyContinue
        Remove-Job $job -Force -ErrorAction SilentlyContinue
        Write-MonitorLog "OVERSEER timeout_90s - cursor_wake queued"
        $wakeCli = Join-Path $ProjectDir "scripts\cursor_wake_cli.py"
        if (Test-Path $wakeCli) { & $python $wakeCli overseer_timeout --detail 'blocked_over_90s' --priority critical 2>$null | Out-Null }
    }
    Remove-Job $job -Force -ErrorAction SilentlyContinue
}

# Graceful reload when swarm queued self-restart - launcher owns restarts when running
$launcherRunning = Test-OwlLauncherRunning

$restartFile = Join-Path $ProjectDir "outputs\restart_pending.json"
$restartCooldownFile = Join-Path $ProjectDir "outputs\last_graceful_restart.json"
$canGracefulRestart = $true
if (Test-Path $restartCooldownFile) {
    try {
        $cool = Get-Content $restartCooldownFile -Raw | ConvertFrom-Json
        $ageSec = (Get-Date).ToUniversalTime().Subtract(
            [datetime]::Parse($cool.ts_utc)
        ).TotalSeconds
        if ($ageSec -lt 300) { $canGracefulRestart = $false }
    } catch { }
}

if ((Test-Path $restartFile) -and $owlPid -and $canGracefulRestart -and -not $launcherRunning) {
    try {
        $restartData = Get-Content $restartFile -Raw | ConvertFrom-Json
        $reason = $restartData.reason
        $reqAge = (Get-Date).ToUniversalTime().Subtract(
            [datetimeOffset]::FromUnixTimeSeconds([int]$restartData.requested_at).UtcDateTime
        ).TotalSeconds
        if ($reqAge -lt 15) { $canGracefulRestart = $false }
    } catch { $reason = "restart_pending.json" }
}

# Never kill owl mid-cycle - defer restart until cycle idle or stale > 15 min
if ((Test-Path $restartFile) -and $owlPid -and $canGracefulRestart -and -not $launcherRunning) {
    $stateFile = Join-Path $ProjectDir "outputs\owl-state.json"
    if (Test-Path $stateFile) {
        try {
            $st = Get-Content $stateFile -Raw | ConvertFrom-Json
            if ($st.last_cycle_at) {
                $cycleAge = (Get-Date).ToUniversalTime().Subtract(
                    [datetimeOffset]::FromUnixTimeSeconds([int]$st.last_cycle_at).UtcDateTime
                ).TotalSeconds
                if ($cycleAge -lt 900) { $canGracefulRestart = $false }
            }
        } catch { }
    }
}

if ((Test-Path $restartFile) -and $owlPid -and $canGracefulRestart -and -not $launcherRunning) {
    Write-MonitorLog "GRACEFUL-RESTART queued: $reason (PID $owlPid)"
    Stop-Process -Id $owlPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    $lockFile = Join-Path $ProjectDir "outputs\owl-llm.lock"
    if (Test-Path $lockFile) { Remove-Item $lockFile -Force }
    Remove-Item $restartFile -Force -ErrorAction SilentlyContinue
    $python = "C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
    $script = Join-Path $ProjectDir "owl_llm_loop.py"
    if ((Test-Path $python) -and (Test-Path $script)) {
        # Hidden window - monitor must never pop visible consoles or Chrome tabs
        $env:OWL_EXTERNAL_DASHBOARD = "1"
        $proc = Start-Process -FilePath $python -ArgumentList "`"$script`"" -PassThru -WindowStyle Hidden -WorkingDirectory $ProjectDir
        Write-MonitorLog "GRACEFUL-RESTART complete PID $($proc.Id)"
        @{ ts_utc = (Get-Date).ToUniversalTime().ToString("o"); pid = $proc.Id } |
            ConvertTo-Json | Set-Content $restartCooldownFile -Encoding UTF8
        $helper = Join-Path $ProjectDir 'scripts\owl_monitor_helper.py'
        & $python $helper save_fingerprint | Out-Null
        & $python $helper graceful_restart --detail graceful --pid $proc.Id | Out-Null
    }
} elseif ((Test-Path $restartFile) -and $owlPid -and $launcherRunning) {
    Write-MonitorLog "GRACEFUL-RESTART deferred to desktop launcher"
} elseif ((Test-Path $restartFile) -and $owlPid) {
    Write-MonitorLog "GRACEFUL-RESTART skipped (cooldown) - will apply between cycles"
}

# Restart WS bridge if owl is up but cache stale
if ($status -eq "HEALTHY" -and -not $wsFresh) {
    $bridgeScript = Join-Path $ProjectDir "scripts\blofin_ws_bridge.mjs"
    if (Test-Path $bridgeScript) {
        if ($wsPid) { Stop-Process -Id $wsPid -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1 }
        $nodeProc = Start-Process -FilePath "node" -ArgumentList "`"$bridgeScript`"" -PassThru -WindowStyle Minimized -WorkingDirectory $ProjectDir
        Write-MonitorLog "WS bridge restarted PID $($nodeProc.Id) (stale cache)"
    }
    # Python REST fallback for tickers
    $pyCache = Join-Path $ProjectDir "scripts\write_universe_cache.py"
    $python = "C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
    if ((Test-Path $python) -and (Test-Path $pyCache)) {
        Start-Process -FilePath $python -ArgumentList "`"$pyCache`"" -WindowStyle Hidden -WorkingDirectory $ProjectDir | Out-Null
    }
}

# Profitability note when margin tight with open positions
if ($available -ne "?" -and [double]$available -lt 0.35 -and [int]$positions -gt 0) {
    Write-MonitorLog "PROFIT_HINT avail=`$$available < 0.35 with $positions pos - profit_guard should bank winners"
}

# Equity stream health - must tick every few seconds (WS mark-to-market)
$streamState = Join-Path $ProjectDir "outputs\equity_stream_state.json"
if (Test-Path $streamState) {
    try {
        $ss = Get-Content $streamState -Raw | ConvertFrom-Json
        $streamAge = [int]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) - [int]$ss.last_tick_at
        if ($streamAge -gt 20 -and $status -eq "HEALTHY") {
            Write-MonitorLog "EQUITY_STREAM stale ${streamAge}s - dashboard should refresh ws marks"
            $wakeCli = Join-Path $ProjectDir "scripts\cursor_wake_cli.py"
            if ((Test-Path $python) -and (Test-Path $wakeCli)) {
                & $python $wakeCli equity_stream_stale --detail "stream_age=${streamAge}s" --priority high 2>$null | Out-Null
            }
        }
    } catch { }
}

# Auto-restart if process dead - defer to launcher when it is running
if ($status -eq "DOWN" -and -not (Test-OwlLauncherRunning)) {
    Clear-StaleOwlLock -ProjectDir $ProjectDir
    $lockFile = Join-Path $ProjectDir "outputs\owl-llm.lock"
    if (Test-Path $lockFile) { Remove-Item $lockFile -Force }
    Ensure-OwlDashboardServer -ProjectDir $ProjectDir | Out-Null
    $python = "C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
    $script = Join-Path $ProjectDir "owl_llm_loop.py"
    if ((Test-Path $python) -and (Test-Path $script)) {
        $env:OWL_EXTERNAL_DASHBOARD = "1"
        $swarmPid = Start-OwlSwarmProcess -ProjectDir $ProjectDir
        Write-MonitorLog "AUTO-RESTART attempted PID $swarmPid"
        Write-Output "AUTO-RESTART PID $swarmPid"
        $helper = Join-Path $ProjectDir 'scripts\owl_monitor_helper.py'
        if ((Test-Path $helper)) {
            & $python $helper stack_down --pid $swarmPid 2>$null
        }
    }
} elseif ($status -eq "DOWN" -and (Test-OwlLauncherRunning)) {
    Write-MonitorLog "DOWN but launcher running - defer restart to launcher"
}
