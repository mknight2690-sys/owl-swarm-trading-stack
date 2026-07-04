param([string]$Prompt, [int]$IntervalSec = 60)
$Sentinel = "AGENT_LOOP_TICK_BAAS_ARCADE"
while ($true) {
    Start-Sleep -Seconds $IntervalSec
    $json = (@{ prompt = $Prompt } | ConvertTo-Json -Compress)
    Write-Output "$Sentinel $json"
}
