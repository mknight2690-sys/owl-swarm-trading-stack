# OWL Swarm - clean shutdown (desktop stopper)
# Kills launcher + ALL bots + dashboards on computer
# Does NOT close your main Chrome browser

$ErrorActionPreference = "Continue"
$ProjectDir = "C:\Users\mknig\owl-swarm"

. (Join-Path $ProjectDir "scripts\owl_common.ps1")

Write-Host "==================================================="
Write-Host "  Stopping ALL OWL bots and dashboards"
Write-Host "  Your main Chrome browser will stay open"
Write-Host "==================================================="

Write-Host "Stopping desktop launcher..."
Stop-OwlLauncher -ProjectDir $ProjectDir

Write-Host "Stopping full OWL stack..."
Stop-AllOwlBotsOnComputer -ProjectDir $ProjectDir

Release-OwlLauncherMutex

$auditDir = Join-Path $ProjectDir "outputs"
if (Test-Path $auditDir) {
    $note = @{
        ts = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        kind = "manual_stop"
        detail = "User ran stop.ps1 - launcher, bots, dashboard server stopped; main Chrome left open"
    } | ConvertTo-Json -Compress
    Add-Content -Path (Join-Path $auditDir "overseer_notes.jsonl") -Value $note -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "All OWL bots and dashboards stopped."
Write-Host "  - Desktop launcher: OFF"
Write-Host "  - Trading loop, monitor, dashboard server: OFF"
Write-Host "  - Port 7878 freed, locks cleared"
Write-Host "  - Your main Chrome browser was NOT closed"
Write-Host ""
