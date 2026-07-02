# Install / refresh OWL Swarm desktop shortcuts (launcher + stopper)
$ErrorActionPreference = "Continue"
$ProjectDir = "C:\Users\mknig\owl-swarm"
$StartBat = Join-Path $ProjectDir "Start-OWL-Swarm.bat"
$StopBat = Join-Path $ProjectDir "Stop-OWL-Swarm.bat"

$targets = @(
    [Environment]::GetFolderPath("Desktop"),
    "C:\Users\mknig\Desktop",
    "C:\Users\mknig\OneDrive\Desktop"
) | Select-Object -Unique

function New-DesktopShortcut {
    param(
        [string]$Folder,
        [string]$Name,
        [string]$Target,
        [string]$Description
    )
    if (-not (Test-Path $Folder)) {
        New-Item -ItemType Directory -Path $Folder -Force | Out-Null
    }
    $path = Join-Path $Folder "$Name.lnk"
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($path)
    $sc.TargetPath = $Target
    $sc.WorkingDirectory = $ProjectDir
    $sc.Description = $Description
    $sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,13"
    $sc.Save()
    Write-Host "Created: $path"
}

foreach ($desktop in $targets) {
    if (-not $desktop) { continue }
    New-DesktopShortcut -Folder $desktop -Name "OWL Swarm" -Target $StartBat -Description "Start OWL Swarm (isolated dashboard, main Chrome untouched)"
    New-DesktopShortcut -Folder $desktop -Name "Stop OWL Swarm" -Target $StopBat -Description "Stop OWL Swarm (main Chrome stays open)"
}

Write-Host ""
Write-Host "Desktop shortcuts updated."
Write-Host "  OWL Swarm      -> $StartBat"
Write-Host "  Stop OWL Swarm -> $StopBat"
