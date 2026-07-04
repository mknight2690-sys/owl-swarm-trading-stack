param([string]$Prompt, [int]$IntervalSec = 60)
$Sentinel = "AGENT_LOOP_TICK_TOKEN_LAUNCH"
while ($true) {
    Start-Sleep -Seconds $IntervalSec
    $json = (@{ prompt = $Prompt } | ConvertTo-Json -Compress)
    Write-Output "$Sentinel $json"
}
