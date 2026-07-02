# Legacy helper - use Start-OWL-Swarm.bat (launch.ps1) for full desktop launcher.
# This script only repairs stack when launcher is NOT running.
$ErrorActionPreference = "Continue"
$ProjectDir = "C:\Users\mknig\owl-swarm"

. (Join-Path $ProjectDir "scripts\owl_common.ps1")

if (Test-OwlLauncherRunning) {
    Write-Host "Desktop launcher is already running - use Stop-OWL-Swarm.bat then Start-OWL-Swarm.bat"
    exit 0
}

Write-Host "Repair mode (no launcher): dashboard + swarm + monitor..."
Close-OwlDashboardTabsOnly -ProjectDir $ProjectDir
Stop-OwlSwarmProcesses -ProjectDir $ProjectDir -KeepDashboardServer

$restartFile = Join-Path $ProjectDir "outputs\restart_pending.json"
if (Test-Path $restartFile) { Remove-Item $restartFile -Force }

if (-not (Ensure-OwlDashboardServer -ProjectDir $ProjectDir -Fresh)) {
    Write-Host "DASHBOARD FAILED"
    exit 1
}

$swarmPid = Start-OwlSwarmProcess -ProjectDir $ProjectDir
if (-not $swarmPid) {
    Write-Host "SWARM START FAILED"
    exit 1
}

& "C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe" -c "import sys; sys.path.insert(0, r'C:\Users\mknig\blofin-auto-trader'); from autohedge.swarm_restart import save_runtime_fingerprint; save_runtime_fingerprint()" 2>$null

Open-OwlDashboardBrowser -ProjectDir $ProjectDir
Write-Host "DONE. Dashboard http://127.0.0.1:7878 | Swarm PID $swarmPid"

Close-DuplicateOwlMonitors -ProjectDir $ProjectDir
$MonitorScript = Join-Path $ProjectDir "scripts\loop_monitor.ps1"
$mon = Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$MonitorScript`"" `
    -PassThru -WindowStyle Hidden -WorkingDirectory $ProjectDir
$mon.Id | Set-Content (Join-Path $ProjectDir "outputs\monitor.pid")
Write-Host "Monitor PID $($mon.Id) (hidden)"
