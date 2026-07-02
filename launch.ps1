# OWL Swarm Desktop Launcher
# - Kills ALL bots + dashboards on computer (single clean slate)
# - Starts exactly ONE dashboard server + ONE swarm stack + ONE monitor
# - Opens ONE isolated dashboard window (main Chrome never closed)
# - Owns graceful restarts (monitor defers when launcher is running)

$ErrorActionPreference = "Continue"
$ProjectDir = "C:\Users\mknig\owl-swarm"
$PidFile = Join-Path $ProjectDir "outputs\owl-swarm.pid"
$LauncherPidFile = Join-Path $ProjectDir "outputs\launcher.pid"
$LogFile = Join-Path $ProjectDir "outputs\launcher.log"
$RestartFile = Join-Path $ProjectDir "outputs\restart_pending.json"
$PythonExe = "C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
$MainScript = Join-Path $ProjectDir "owl_llm_loop.py"
$MonitorScript = Join-Path $ProjectDir "scripts\loop_monitor.ps1"
$DashboardURL = "http://127.0.0.1:7878"
$MutexName = "Global\OWL_Swarm_SingleInstance"

. (Join-Path $ProjectDir "scripts\owl_common.ps1")

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line -ForegroundColor Cyan
    $outDir = Join-Path $ProjectDir "outputs"
    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value $line -ErrorAction SilentlyContinue
}

function Acquire-Mutex {
    param([int]$Retries = 8)

    for ($attempt = 1; $attempt -le $Retries; $attempt++) {
        try {
            $createdNew = $false
            $script:mutex = New-Object System.Threading.Mutex($false, $MutexName, [ref]$createdNew)
            if ($script:mutex.WaitOne(2000)) {
                if ($attempt -gt 1) {
                    Write-Log "Mutex acquired on attempt $attempt"
                }
                return $true
            }
            $script:mutex.Dispose()
            $script:mutex = $null
        } catch {
            $script:mutex = $null
        }
        Write-Log "Mutex busy (attempt $attempt/$Retries) - waiting for prior launcher to release..."
        Start-Sleep -Seconds 1
    }
    Write-Log "ERROR: Could not acquire launcher mutex after $Retries attempts."
    return $false
}

function Save-RuntimeFingerprint {
    if (-not (Test-Path $PythonExe)) { return }
    & $PythonExe -c "import sys; sys.path.insert(0, r'C:\Users\mknig\blofin-auto-trader'); from autohedge.swarm_restart import save_runtime_fingerprint; save_runtime_fingerprint()" 2>$null | Out-Null
}

function Start-SwarmProcess {
    Write-Log "Starting OWL Swarm (Multi-LLM Python)..."
    Set-Location $ProjectDir

    if (-not (Test-Path $PythonExe)) {
        Write-Log "Python not found at $PythonExe"
        return $null
    }
    if (-not (Test-Path $MainScript)) {
        Write-Log "Main script not found: $MainScript"
        return $null
    }

    $swarmPid = Start-OwlSwarmProcess -ProjectDir $ProjectDir
    if (-not $swarmPid) {
        Write-Log "Failed to spawn owl_llm_loop"
        return $null
    }

    Start-Sleep -Seconds 4
    $proc = Get-Process -Id $swarmPid -ErrorAction SilentlyContinue
    if (-not $proc) {
        $errLog = Join-Path $ProjectDir "outputs\owl-stderr.log"
        $tail = ""
        if (Test-Path $errLog) {
            $tail = (Get-Content $errLog -Tail 8 -ErrorAction SilentlyContinue) -join " | "
        }
        Write-Log "OWL Swarm exited immediately (PID $swarmPid). stderr: $tail"
        return $null
    }

    Write-Log "OWL Swarm started (PID: $swarmPid)"
    return $proc
}

function Start-HealthMonitor {
    if (-not (Test-Path $MonitorScript)) {
        Write-Log "WARN: loop_monitor.ps1 not found - skipping 1-min health monitor"
        return $null
    }
    Close-DuplicateOwlMonitors -ProjectDir $ProjectDir
    Write-Log "Starting 1-minute health monitor (hidden)..."
    $mon = Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$MonitorScript`"" `
        -PassThru -WindowStyle Hidden -WorkingDirectory $ProjectDir
    $mon.Id | Set-Content (Join-Path $ProjectDir "outputs\monitor.pid")
    Write-Log "Health monitor started (PID: $($mon.Id))"
    return $mon
}

function Test-DashboardReady {
    Test-OwlDashboardHealthy
}

function Open-DashboardInChrome {
    if (-not (Test-DashboardReady)) {
        Write-Log "Dashboard API not ready - NOT opening browser (prevents dead tabs)"
        return
    }
    Write-Log "Opening single isolated OWL dashboard window"
    Open-OwlDashboardBrowser -ProjectDir $ProjectDir -Url $DashboardURL -Force
}

function Get-RestartReason {
    if (-not (Test-Path $RestartFile)) { return $null }
    try {
        $data = Get-Content $RestartFile -Raw | ConvertFrom-Json
        return $data.reason
    } catch {
        return "restart_pending.json present"
    }
}

function Get-OwlSwarmProcess {
    $py = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*owl_llm_loop*' } |
        Select-Object -First 1
    if ($py) {
        return Get-Process -Id $py.ProcessId -ErrorAction SilentlyContinue
    }
    return $null
}

function Restart-SwarmGracefully {
    param($Reason)
    Write-Log "GRACEFUL RESTART: $Reason"
    if ($script:swarmProc -and -not $script:swarmProc.HasExited) {
        Write-Log "Stopping current swarm PID $($script:swarmProc.Id)..."
        Stop-Process -Id $script:swarmProc.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
    }
    if (Test-Path $RestartFile) { Remove-Item $RestartFile -Force -ErrorAction SilentlyContinue }
    Clear-StaleOwlLock -ProjectDir $ProjectDir
    Ensure-OwlDashboardServer -ProjectDir $ProjectDir | Out-Null
    $script:swarmProc = Start-SwarmProcess
    Save-RuntimeFingerprint
    if ($script:swarmProc) {
        Start-Sleep -Seconds 5
    }
}

# -----------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------
Write-Log "==================================================="
Write-Log "  OWL Swarm Desktop Launcher (Multi-LLM)"
Write-Log "  Kill all bots + dashboards | single instance boot"
Write-Log "==================================================="

$PID | Set-Content $LauncherPidFile

Write-Log "Phase 1: Kill ALL bots and dashboards (fast boot)..."
Stop-AllOwlBotsOnComputer -ProjectDir $ProjectDir -PreserveLauncherPid $PID -FastBoot

if (Test-Path $RestartFile) { Remove-Item $RestartFile -Force -ErrorAction SilentlyContinue }

Write-Log "Phase 2: Acquire single-instance lock..."
if (-not (Acquire-Mutex)) {
    Write-Log "FATAL: Another launcher still holds the mutex. Close other OWL launcher windows and retry."
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Log "Phase 3: Start single dashboard server..."
$env:OWL_EXTERNAL_DASHBOARD = "1"
if (-not (Ensure-OwlDashboardServer -ProjectDir $ProjectDir -Fresh)) {
    Write-Log "Failed to start dashboard server!"
    $script:mutex.ReleaseMutex()
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Log "Phase 4: Start single OWL swarm stack..."
$script:swarmProc = Start-SwarmProcess
if (-not $script:swarmProc) {
    Write-Log "Failed to start OWL Swarm!"
    $script:mutex.ReleaseMutex()
    Read-Host "Press Enter to exit"
    exit 1
}

Save-RuntimeFingerprint
$script:monitorProc = Start-HealthMonitor

if (-not (Test-OwlStackSingleInstance -ProjectDir $ProjectDir)) {
    Write-Log "WARN: duplicate processes detected after boot - repairing (launcher kept alive)..."
    Repair-OwlStackDuplicates -ProjectDir $ProjectDir
    Ensure-OwlDashboardServer -ProjectDir $ProjectDir | Out-Null
    $existing = Get-OwlSwarmProcess
    if ($existing) {
        $script:swarmProc = $existing
        Write-Log "Tracking existing swarm PID $($existing.Id)"
    } elseif ($script:swarmProc -and -not $script:swarmProc.HasExited) {
        Write-Log "Keeping launcher-spawned swarm PID $($script:swarmProc.Id)"
    } else {
        $script:swarmProc = Start-SwarmProcess
    }
    if (-not $script:monitorProc -or $script:monitorProc.HasExited) {
        $script:monitorProc = Start-HealthMonitor
    }
}

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    if (Test-DashboardReady) {
        try {
            $homeResp = Invoke-WebRequest -Uri "$DashboardURL/" -UseBasicParsing -TimeoutSec 5
            if ($homeResp.Content -match 'OWL') { $ready = $true; break }
        } catch { }
    }
    Start-Sleep -Seconds 1
}
if (-not $ready) {
    Write-Log "Dashboard not responding - will NOT open browser until API is up"
} else {
    Open-DashboardInChrome
}

Write-Log "Monitor loop: dashboard + swarm health + restart_pending.json every 10s"
Write-Log "Dashboard: $DashboardURL | Main Chrome is never closed by this launcher"
$restartCount = 0
$script:dashLastEnsure = $null
while ($true) {
    Start-Sleep -Seconds 10

    if (-not (Test-DashboardReady)) {
        $cooldownOk = (-not $script:dashLastEnsure) -or (((Get-Date) - $script:dashLastEnsure).TotalSeconds -ge 60)
        if ($cooldownOk) {
            Write-Log "Dashboard unhealthy - ensuring server (no kill unless dead)..."
            Ensure-OwlDashboardServer -ProjectDir $ProjectDir | Out-Null
            $script:dashLastEnsure = Get-Date
        }
    }

    $pendingReason = Get-RestartReason
    if ($pendingReason) {
        $restartCount++
        Restart-SwarmGracefully -Reason $pendingReason
        continue
    }

    if ($script:swarmProc -and $script:swarmProc.HasExited) {
        $existing = Get-OwlSwarmProcess
        if ($existing) {
            Write-Log "Swarm self-restarted in-process - now tracking PID $($existing.Id)"
            $script:swarmProc = $existing
            $existing.Id | Set-Content $PidFile
            continue
        }
        $restartCount++
        Write-Log "Swarm process died! Restart #$restartCount (exit $($script:swarmProc.ExitCode))"
        Start-Sleep -Seconds 3
        Ensure-OwlDashboardServer -ProjectDir $ProjectDir | Out-Null
        $script:swarmProc = Start-SwarmProcess
        Save-RuntimeFingerprint
        if ($script:swarmProc) {
            Start-Sleep -Seconds 5
        }
    }

    if ($script:monitorProc -and $script:monitorProc.HasExited) {
        Write-Log "Health monitor died - restarting loop_monitor.ps1"
        $script:monitorProc = Start-HealthMonitor
    }
}
