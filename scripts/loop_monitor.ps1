# 1-minute OWL Swarm monitor loop - ONE hidden PowerShell, no nested windows
$ErrorActionPreference = "SilentlyContinue"
$ProjectDir = "C:\Users\mknig\owl-swarm"
$MonitorScript = Join-Path $ProjectDir "scripts\monitor_health.ps1"

. (Join-Path $ProjectDir "scripts\owl_common.ps1")

while ($true) {
    Start-Sleep -Seconds 60
    try {
        # Run in THIS process - never spawn another powershell.exe (that was stacking windows)
        & $MonitorScript
    } catch {
        Write-Host "monitor tick error: $_"
    }
}
