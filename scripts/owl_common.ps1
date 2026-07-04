# Shared kill/cleanup helpers for OWL Swarm launcher and stopper
$ErrorActionPreference = "SilentlyContinue"

function Close-OwlDashboardTabsOnly {
    param([string]$ProjectDir)

    # TAB ONLY - never Stop-Process chrome.exe (that kills the whole browser)
    $py = "C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
    $script = Join-Path $ProjectDir "scripts\close_dashboard_tabs_only.py"
    if ((Test-Path $py) -and (Test-Path $script)) {
        & $py $script 2>&1 | Out-Host
    } else {
        Write-Host "  Tab-only closer not found - skipping (Chrome left untouched)"
    }
}

function Close-StaleDashboardBrowsers {
    param([string]$ProjectDir)
    Close-OwlDashboardTabsOnly -ProjectDir $ProjectDir
}

function Close-OwlIsolatedDashboardWindow {
    param([string]$ProjectDir)
    $py = "C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
    $script = Join-Path $ProjectDir "scripts\close_dashboard_tabs_only.py"
    if ((Test-Path $py) -and (Test-Path $script)) {
        & $py $script 2>&1 | Out-Null
    }
}

function Test-OwlDashboardBrowserOpen {
    param([string]$ProjectDir)
    $profile = Join-Path $ProjectDir "outputs\owl-chrome-profile"
    $hit = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$profile*" } |
        Select-Object -First 1
    return [bool]$hit
}

function Test-OwlDashboardApiReady {
    param([string]$Url = "http://127.0.0.1:7878/api/status")
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 8
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Test-OwlDashboardPortListening {
  param([int]$Port = 7878)
  try {
    $listener = netstat -ano | Select-String ":$Port\s" | Select-String "LISTENING" | Select-Object -First 1
    return [bool]$listener
  } catch {
    return $false
  }
}

function Get-OwlDashboardProcess {
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*dashboard_server.py*' } |
    Select-Object -First 1
}

function Test-OwlDashboardHealthy {
  # API fast path
  if (Test-OwlDashboardApiReady) { return $true }
  # Server process + port = alive (API may be slow during Blofin refresh)
  $proc = Get-OwlDashboardProcess
  if ($proc -and (Test-OwlDashboardPortListening)) { return $true }
  return $false
}

function Close-DuplicateOwlMonitors {
    param([string]$ProjectDir)

    $out = Join-Path $ProjectDir "outputs"
    $keeperPid = 0
    $monitorPidFile = Join-Path $out "monitor.pid"
    if (Test-Path $monitorPidFile) {
        try { $keeperPid = [int](Get-Content $monitorPidFile -Raw).Trim() } catch { }
    }

    $myPid = $PID
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            ($_.CommandLine -like '*loop_monitor.ps1*' -or
             $_.CommandLine -like '*monitor_health.ps1*') -and
            $_.ProcessId -ne $myPid -and
            ($keeperPid -eq 0 -or $_.ProcessId -ne $keeperPid)
        } |
        ForEach-Object {
            Write-Host "  Close duplicate monitor PS PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

function Stop-AllOwlBotsOnComputer {
    param(
        [string]$ProjectDir,
        [int]$PreserveLauncherPid = 0,
        [switch]$FastBoot
    )

    Write-Host "Killing ALL trading bots and dashboards on this computer..."
    if ($FastBoot) {
        Write-Host "  (fast boot - tab cleanup deferred until dashboard opens)"
    } else {
        Write-Host "  (main Chrome browser is NOT closed - isolated OWL window only)"
    }

    if ($PreserveLauncherPid -eq 0) {
        Stop-OwlLauncher -ProjectDir $ProjectDir
    }

    $myPid = $PID
    $killed = @{}

    function Stop-PidSafe([int]$procId, [string]$label) {
        if ($procId -le 0 -or $procId -eq $myPid) { return }
        if ($killed.ContainsKey($procId)) { return }
        $killed[$procId] = $true
        Write-Host "  Kill $label PID $procId"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }

    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $c = $_.CommandLine
            if (-not $c) { return $false }
            $c -like '*owl_llm_loop*' -or
            $c -like '*swarm.py*' -or
            $c -like '*owl_isolated*' -or
            $c -like '*dashboard_server.py*' -or
            $c -like '*overseer_tick*' -or
            $c -like '*run_blofin_loop*' -or
            $c -like '*watch_and_fix*' -or
            $c -like '*watch_new_trades*' -or
            $c -like '*owl-swarm*' -or
            ($c -like '*blofin-auto-trader*' -and $c -like '*autohedge*')
        } |
        ForEach-Object { Stop-PidSafe $_.ProcessId "python" }

    Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $c = $_.CommandLine
            $c -and (
                $c -like '*blofin_ws_bridge*' -or
                $c -like '*owl-swarm*' -or
                $c -like '*dist\main.js*' -or
                $c -like '*orchestrator*'
            )
        } |
        ForEach-Object { Stop-PidSafe $_.ProcessId "node" }

    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ProcessId -ne $myPid -and $_.ProcessId -ne $PreserveLauncherPid -and $_.CommandLine -and (
                $_.CommandLine -like '*loop_monitor.ps1*' -or
                $_.CommandLine -like '*monitor_health.ps1*' -or
                $_.CommandLine -like '*launch.ps1*' -or
                $_.CommandLine -like '*Run-Blofin-AutoHedge.ps1*' -or
                $_.CommandLine -like '*run_blofin_loop*'
            )
        } |
        ForEach-Object { Stop-PidSafe $_.ProcessId "powershell" }

    netstat -ano | Select-String ":7878" | Select-String "LISTENING" | ForEach-Object {
        $parts = ($_ -split '\s+') | Where-Object { $_ -ne '' }
        $portPid = $parts[-1]
        if ($portPid -match '^\d+$') {
            Stop-PidSafe ([int]$portPid) "port-7878"
        }
    }

    Start-Sleep -Seconds $(if ($FastBoot) { 1 } else { 2 })

    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $c = $_.CommandLine
            $c -and (
                $c -like '*owl_llm_loop*' -or
                $c -like '*dashboard_server.py*' -or
                $c -like '*run_blofin_loop*'
            )
        } |
        ForEach-Object { Stop-PidSafe $_.ProcessId "python-straggler" }

    if (-not $FastBoot) {
        Close-OwlIsolatedDashboardWindow -ProjectDir $ProjectDir
        Close-OwlDashboardTabsOnly -ProjectDir $ProjectDir
    }

    $out = Join-Path $ProjectDir "outputs"
    $autoOut = "C:\Users\mknig\blofin-auto-trader\outputs"
    $clearFiles = @(
        "owl-llm.lock",
        "owl-swarm.pid",
        "monitor.pid",
        "dashboard-server.pid",
        "restart_pending.json"
    )
    if ($PreserveLauncherPid -eq 0) {
        $clearFiles += "launcher.pid"
    }
    $clearFiles | ForEach-Object {
        $f = Join-Path $out $_
        if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
    }
    @("blofin-loop.lock", "blofin-loop-shell.lock") | ForEach-Object {
        $f = Join-Path $autoOut $_
        if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
    }

    Write-Host "  All bots and dashboards stopped."
}

function Test-OwlLockHolderValid {
    param(
        [string]$ProjectDir,
        [int]$Pid = 0
    )
    if ($Pid -le 0) { return $false }
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$Pid" -ErrorAction SilentlyContinue
        if (-not $proc) { return $false }
        return ($proc.CommandLine -like '*owl_llm_loop*')
    } catch {
        return $false
    }
}

function Clear-StaleOwlLock {
    param([string]$ProjectDir)

    $lockFile = Join-Path $ProjectDir "outputs\owl-llm.lock"
    if (-not (Test-Path $lockFile)) { return }

    $holder = 0
    try { $holder = [int](Get-Content $lockFile -Raw).Trim() } catch { $holder = 0 }

    if ($holder -le 0) {
        Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
        return
    }

    if (-not (Test-OwlLockHolderValid -ProjectDir $ProjectDir -Pid $holder)) {
        Write-Host "  Clear stale owl-llm.lock (PID $holder not a valid owl_llm_loop)"
        Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    }
}

function Get-OwlLauncherProcess {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*launch.ps1*' } |
        Select-Object -First 1
}

function Test-OwlLauncherRunning {
    return [bool](Get-OwlLauncherProcess)
}

function Stop-OwlLauncher {
    param(
        [string]$ProjectDir,
        [int]$ExcludePid = 0
    )

    $launcherPidFile = Join-Path $ProjectDir "outputs\launcher.pid"
    $keeper = 0
    if (Test-Path $launcherPidFile) {
        try { $keeper = [int](Get-Content $launcherPidFile -Raw).Trim() } catch { }
    }

    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -like '*launch.ps1*' -and
            $_.ProcessId -ne $ExcludePid
        } |
        ForEach-Object {
            Write-Host "  Kill launcher PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }

    if ($keeper -gt 0 -and $keeper -ne $ExcludePid) {
        Stop-Process -Id $keeper -Force -ErrorAction SilentlyContinue
    }

    if ($ExcludePid -eq 0 -and (Test-Path $launcherPidFile)) {
        Remove-Item $launcherPidFile -Force -ErrorAction SilentlyContinue
    }
}

function Repair-OwlStackDuplicates {
    param(
        [string]$ProjectDir,
        [int[]]$PreservePids = @()
    )

    Clear-StaleOwlLock -ProjectDir $ProjectDir

    $owlProcs = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*owl_llm_loop*' })

    if ($owlProcs.Count -gt 1) {
        $lockFile = Join-Path $ProjectDir "outputs\owl-llm.lock"
        $keeper = 0
        if (Test-Path $lockFile) {
            try { $keeper = [int](Get-Content $lockFile -Raw).Trim() } catch { }
        }
        if (-not (Test-OwlLockHolderValid -ProjectDir $ProjectDir -Pid $keeper)) {
            $keeper = ($owlProcs | Sort-Object CreationDate -Descending | Select-Object -First 1).ProcessId
        }
        foreach ($proc in $owlProcs) {
            if ($proc.ProcessId -eq $keeper) { continue }
            if ($PreservePids -contains $proc.ProcessId) { continue }
            Write-Host "  Kill duplicate owl_llm_loop PID $($proc.ProcessId)"
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }

    $dashProcs = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*dashboard_server.py*' })
    if ($dashProcs.Count -gt 1) {
        $keeperDash = ($dashProcs | Sort-Object CreationDate -Descending | Select-Object -First 1).ProcessId
        foreach ($proc in $dashProcs) {
            if ($proc.ProcessId -eq $keeperDash) { continue }
            Write-Host "  Kill duplicate dashboard_server PID $($proc.ProcessId)"
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }

    Close-DuplicateOwlMonitors -ProjectDir $ProjectDir
}

function Ensure-OwlDashboardServer {
    param(
        [string]$ProjectDir,
        [switch]$Fresh
    )

    if (-not $Fresh -and (Test-OwlDashboardHealthy)) {
        return $true
    }

    # Process alive but API/port flaky — do not kill; wait for recovery
    $existing = Get-OwlDashboardProcess
    if (-not $Fresh -and $existing -and (Test-OwlDashboardPortListening)) {
        for ($i = 0; $i -lt 8; $i++) {
            Start-Sleep -Seconds 1
            if (Test-OwlDashboardApiReady) { return $true }
        }
        return $true
    }

    $pid = Start-OwlDashboardServer -ProjectDir $ProjectDir -Fresh:$Fresh
    if (-not $pid) { return $false }

    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        if (Test-OwlDashboardHealthy) { return $true }
    }
    return $false
}

function Release-OwlLauncherMutex {
    try {
        $m = New-Object System.Threading.Mutex($false, "Global\OWL_Swarm_SingleInstance")
        $m.ReleaseMutex() | Out-Null
        $m.Dispose()
    } catch {
        # Mutex not held by this process — ignore
    }
}

function Start-OwlSwarmProcess {
    param([string]$ProjectDir)

    $python = "C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
    $script = Join-Path $ProjectDir "owl_llm_loop.py"
    $pidFile = Join-Path $ProjectDir "outputs\owl-swarm.pid"
    $stderrLog = Join-Path $ProjectDir "outputs\owl-stderr.log"

    if (-not (Test-Path $python) -or -not (Test-Path $script)) { return 0 }

    Clear-StaleOwlLock -ProjectDir $ProjectDir
    Remove-Item (Join-Path $ProjectDir "outputs\restart_pending.json") -Force -ErrorAction SilentlyContinue

    $env:OWL_EXTERNAL_DASHBOARD = "1"
    $env:OUTPUT_DIR = Join-Path $ProjectDir "outputs"
    $env:BLOFIN_MARGIN_MODE = "isolated"
    $env:OWL_ALLOW_DETERMINISTIC_RISK = "1"
    $env:OWL_DILIGENCE_LLM_N = "2"
    $env:OWL_DILIGENCE_WAIT_SEC = "20"
    $env:OWL_SUPPORT_WAIT_SEC = "8"
    $env:OWL_DIRECTOR_TIMEOUT_SEC = "120"
    $env:CYCLE_INTERVAL_S = "90"
    $env:OWL_SKIP_OPS_LLM = "0"
    $env:OWL_SKIP_PENTEST = "0"
    $env:OWL_PENTEST_INTERVAL_SEC = "30"
    $env:OWL_PENTEST_SCOUT_LLM = "1"
    $env:OWL_PENTEST_ALWAYS_LLM = "1"
    $env:OWL_PICK_BEST_CHECK_N = "20"
    $env:OWL_FAST_TRY_N = "8"
    $env:AUTOHEDGE_MODEL = "nvidia_nim/z-ai/glm-5.1"
    $env:NVIDIA_NIM_API_BASE = "https://integrate.api.nvidia.com/v1"
    # $env:NVIDIA_NIM_API_BASE = "https://llm-knightrader.your-endpoint.com/v1"  # Uncomment for custom endpoint

    $proc = Start-Process -FilePath $python -ArgumentList "`"$script`"" `
        -PassThru -WindowStyle Hidden -WorkingDirectory $ProjectDir `
        -RedirectStandardError $stderrLog
    $proc.Id | Set-Content $pidFile
    return $proc.Id
}

function Get-OwlStackCounts {
    $owl = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*owl_llm_loop*' }).Count
    $dash = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*dashboard_server.py*' }).Count
    $mon = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*loop_monitor.ps1*' }).Count
    return @{ owl = $owl; dashboard = $dash; monitor = $mon }
}

function Test-OwlStackSingleInstance {
    param([string]$ProjectDir)
    $c = Get-OwlStackCounts
    $ok = ($c.owl -eq 1) -and ($c.dashboard -eq 1) -and ($c.monitor -le 1)
    if (-not $ok) {
        Write-Host "  WARN: stack counts owl=$($c.owl) dashboard=$($c.dashboard) monitor=$($c.monitor)"
    }
    return $ok
}

function Close-StaleOwlDesktopWindows {
    param([string]$ProjectDir)
    Write-Host "Desktop hygiene: close dashboard TABS only + duplicate monitors (Chrome stays open)..."
    Close-OwlDashboardTabsOnly -ProjectDir $ProjectDir
    Close-DuplicateOwlMonitors -ProjectDir $ProjectDir
}

function Open-OwlDashboardBrowser {
    param(
        [string]$ProjectDir,
        [string]$Url = "http://127.0.0.1:7878",
        [switch]$Force
    )

    if (-not (Test-OwlDashboardApiReady -Url "$Url/api/status")) {
        Write-Host "Dashboard API not ready at $Url - refusing to open browser tab"
        return
    }

    if ($Force) {
        Close-OwlIsolatedDashboardWindow -ProjectDir $ProjectDir
    } elseif (Test-OwlDashboardBrowserOpen -ProjectDir $ProjectDir) {
        Write-Host "OWL dashboard window already open (isolated profile)"
        return
    }

    $chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    $altChrome = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    $profileDir = Join-Path $ProjectDir "outputs\owl-chrome-profile"
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    $chromeArgs = "--user-data-dir=`"$profileDir`" --remote-debugging-port=9223 --app=$Url"

    if (Test-Path $chromePath) {
        Start-Process $chromePath -ArgumentList $chromeArgs -WindowStyle Normal | Out-Null
        Write-Host "Dashboard opened in isolated OWL window (main Chrome untouched)"
    } elseif (Test-Path $altChrome) {
        Start-Process $altChrome -ArgumentList $chromeArgs -WindowStyle Normal | Out-Null
        Write-Host "Dashboard opened in isolated OWL window (main Chrome untouched)"
    } else {
        Start-Process "msedge" -ArgumentList "--app=$Url" -WindowStyle Normal | Out-Null
        Write-Host "Dashboard opened in Edge app window"
    }
}

function Start-OwlDashboardServer {
    param(
        [string]$ProjectDir,
        [switch]$Fresh
    )

    $python = "C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
    $script = Join-Path $ProjectDir "scripts\dashboard_server.py"
    $pidFile = Join-Path $ProjectDir "outputs\dashboard-server.pid"

    if ($Fresh) {
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like '*dashboard_server.py*' } |
            ForEach-Object {
                Write-Host "  Kill old dashboard server PID $($_.ProcessId)"
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            }
        Start-Sleep -Seconds 1
    } else {
        $existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like '*dashboard_server.py*' } |
            Select-Object -First 1
        if ($existing) {
            $existing.ProcessId | Set-Content $pidFile
            return $existing.ProcessId
        }
    }

    if (-not (Test-Path $python) -or -not (Test-Path $script)) {
        Write-Host "Dashboard server script missing"
        return 0
    }

    $proc = Start-Process -FilePath $python -ArgumentList "`"$script`"" -PassThru -WindowStyle Hidden -WorkingDirectory $ProjectDir
    $proc.Id | Set-Content $pidFile
    Write-Host "Dashboard server started PID $($proc.Id)"
    return $proc.Id
}

function Stop-OwlSwarmProcesses {
    param(
        [string]$ProjectDir,
        [switch]$KeepDashboardServer
    )

    if ($KeepDashboardServer) {
        Write-Host "Stopping OWL Swarm processes (keeping dashboard server)..."
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object {
                ($_.CommandLine -like '*owl_llm_loop*' -or $_.CommandLine -like '*overseer_tick*') -and
                $_.CommandLine -notlike '*dashboard_server.py*'
            } |
            ForEach-Object {
                Write-Host "  Kill python PID $($_.ProcessId)"
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            }
    } else {
        Stop-AllOwlBotsOnComputer -ProjectDir $ProjectDir
        return
    }

    Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*blofin_ws_bridge*' -or $_.CommandLine -like '*owl-swarm*' } |
        ForEach-Object {
            Write-Host "  Kill node PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }

    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*loop_monitor.ps1*' -or $_.CommandLine -like '*monitor_health.ps1*' } |
        ForEach-Object {
            Write-Host "  Kill monitor PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }

    $out = Join-Path $ProjectDir "outputs"
    @("owl-llm.lock", "owl-swarm.pid", "monitor.pid", "restart_pending.json") | ForEach-Object {
        $f = Join-Path $out $_
        if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
    }

    Start-Sleep -Seconds 1
    Write-Host "OWL Swarm processes stopped. Your main Chrome was NOT closed."
}
