# Close broken OWL dashboard TABS only - never closes Chrome browser
$ProjectDir = "C:\Users\mknig\owl-swarm"
. (Join-Path $ProjectDir "scripts\owl_common.ps1")
Write-Host "Closing OWL dashboard tabs only (main Chrome stays open)..."
Close-OwlDashboardTabsOnly -ProjectDir $ProjectDir
Write-Host "Done."
