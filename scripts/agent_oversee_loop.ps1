# Cursor Agent wake loop — 1-minute redundancy over local monitor (NOT a substitute).
# Emits AGENT_LOOP_TICK_owl_oversee so Cursor is notified to oversee, not only scripts.
$ErrorActionPreference = "SilentlyContinue"
$ProjectDir = "C:\Users\mknig\owl-swarm"
$Python = "C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe"
$AutoRoot = "C:\Users\mknig\blofin-auto-trader"
$PidFile = Join-Path $ProjectDir "outputs\agent_oversee_loop.pid"
$LogFile = Join-Path $ProjectDir "outputs\agent_oversee_loop.log"

function Write-LoopLog($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$ts] $msg" -ErrorAction SilentlyContinue
}

$PID | Set-Content $PidFile -Encoding UTF8
Write-LoopLog "agent_oversee_loop started pid=$PID"

# Heartbeat: local monitor still runs stack repairs
$MonitorScript = Join-Path $ProjectDir "scripts\monitor_health.ps1"
. (Join-Path $ProjectDir "scripts\owl_common.ps1")

while ($true) {
  try {
    & $MonitorScript | Out-Null
  } catch {
    Write-LoopLog "monitor_health error: $_"
  }

  try {
    $payloadScript = Join-Path $ProjectDir "scripts\oversee_tick_payload.py"
    $payload = (& $Python $payloadScript 2>&1 | Out-String).Trim()
    if (-not $payload) { $payload = '{"prompt":"OWL oversee tick"}' }
    $line = "AGENT_LOOP_TICK_owl_oversee $payload"
    Write-Output $line
    Write-LoopLog "tick emitted"
  } catch {
    Write-Output 'AGENT_LOOP_TICK_owl_oversee {"prompt":"OWL oversee tick — read monitor.log and cursor_wake.json"}'
    Write-LoopLog "payload error: $_"
  }

  Start-Sleep -Seconds 60
}
