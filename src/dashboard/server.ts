/** OWL Swarm Dashboard Server — Real-time browser GUI */

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { logger } from "../utils/logger.js";
import { symbolStats, loadEvents } from "../journal/journal.js";
import { findMatchingSkills, getActiveConstraints } from "../skills/library.js";

const PORT = Number(process.env["DASHBOARD_PORT"] ?? 7878);
const HOST = process.env["DASHBOARD_HOST"] ?? "127.0.0.1";
const OUTPUT_DIR = process.env["OUTPUT_DIR"] ?? "outputs";
const POLL_INTERVAL_MS = 500; // live equity refresh every 500ms (max)

export interface SwarmStatus {
  running: boolean;
  cycleCount: number;
  totalTrades: number;
  lastCycleAt: number;
  lastError: string;
  equity: number;
  available: number;
  openPositions: unknown[];
  recentEvents: unknown[];
  skills: number;
  constraints: number;
  agentsActive: number;
  verificationPassRate: number;
}

let currentStatus: SwarmStatus = {
  running: false,
  cycleCount: 0,
  totalTrades: 0,
  lastCycleAt: 0,
  lastError: "",
  equity: 0,
  available: 0,
  openPositions: [],
  recentEvents: [],
  skills: 0,
  constraints: 0,
  agentsActive: 0,
  verificationPassRate: 100,
};

// Ring buffer of recent events for SSE push
const eventBuffer: Array<Record<string, unknown> & { ts: number }> = [];
const MAX_EVENTS = 200;

function broadcast(obj: object) {
  const data = JSON.stringify(obj);
  for (const client of sseClients) {
    try { client.write(`data: ${data}\n\n`); } catch { sseClients.delete(client); }
  }
}

/** Called by orchestrator to push a status update */
export function updateStatus(partial: Partial<SwarmStatus>) {
  Object.assign(currentStatus, partial);
  broadcast({ type: "status", data: { ...currentStatus } });
}

/** Called by orchestrator to push a log/cycle/trade event */
export function addDashboardEvent(event: Record<string, unknown>) {
  const entry = { ...event, ts: Date.now() };
  eventBuffer.push(entry);
  if (eventBuffer.length > MAX_EVENTS) eventBuffer.shift();
  broadcast(entry);
}

const sseClients = new Set<http.ServerResponse>();

export function startDashboardServer(): http.Server {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url ?? "/", `http://${HOST}:${PORT}`);

    if (url.pathname === "/") {
      res.writeHead(200, { "Content-Type": "text/html" });
      res.end(DASHBOARD_HTML);
      return;
    }

    if (url.pathname === "/api/status") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(currentStatus));
      return;
    }

    if (url.pathname === "/api/positions") {
      try {
        const posFile = path.join(OUTPUT_DIR, "positions-cache.json");
        const data = fs.existsSync(posFile) ? JSON.parse(fs.readFileSync(posFile, "utf-8")) : {};
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(data));
      } catch { res.writeHead(200, { "Content-Type": "application/json" }); res.end("{}"); }
      return;
    }

    if (url.pathname === "/api/journal") {
      try {
        const events = loadEvents(50);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ events, stats: symbolStats() }));
      } catch { res.writeHead(200, { "Content-Type": "application/json" }); res.end("[]"); }
      return;
    }

    if (url.pathname === "/api/skills") {
      try {
        const skillsList = findMatchingSkills(".*");
        const constraintsList = getActiveConstraints();
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ skills: skillsList, constraints: constraintsList }));
      } catch { res.writeHead(200, { "Content-Type": "application/json" }); res.end("{}"); }
      return;
    }

    if (url.pathname === "/api/events") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(eventBuffer.slice(-50)));
      return;
    }

    if (url.pathname === "/events") {
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
      });
      // Send current status immediately on connect
      res.write(`data: ${JSON.stringify({ type: "status", data: currentStatus })}\n\n`);
      // Send recent events
      for (const evt of eventBuffer.slice(-20)) {
        res.write(`data: ${JSON.stringify(evt)}\n\n`);
      }
      sseClients.add(res);
      req.on("close", () => sseClients.delete(res));
      return;
    }

    res.writeHead(404);
    res.end("Not found");
  });

  server.listen(PORT, HOST, () => {
    logger.info(`Dashboard server running at http://${HOST}:${PORT}`);
    startLivePoller();
  });

  return server;
}

/** Fast background poller — reads equity/positions from trading engine disk cache every 500ms */
function startLivePoller() {
  const BLOFIN_ROOT = process.env["BLOFIN_ROOT"] ?? "C:\\Users\\mknig\\blofin-auto-trader";

  setInterval(() => {
    try {
      // Read actual Blofin equity from trading engine disk cache
      let equity = 0;
      let available = 0;
      const eqFile = path.join(BLOFIN_ROOT, "outputs", "equity-cache.json");
      if (fs.existsSync(eqFile)) {
        const raw = JSON.parse(fs.readFileSync(eqFile, "utf-8"));
        equity = Number(raw.equity_usdt ?? 0);
        available = Number(raw.available_usdt ?? 0);
      }

      // Read actual Blofin positions from trading engine disk cache
      let positions: unknown[] = [];
      const posFile = path.join(BLOFIN_ROOT, "outputs", "positions-cache.json");
      if (fs.existsSync(posFile)) {
        const raw = JSON.parse(fs.readFileSync(posFile, "utf-8"));
        positions = raw.open_rows ?? [];
      }

      // Update current status
      currentStatus.equity = equity;
      currentStatus.available = available;
      currentStatus.openPositions = positions;
      currentStatus.lastCycleAt = Date.now();

      // Push to all SSE clients
      const msg = JSON.stringify({
        type: "live",
        data: { equity, available, positions, ts: Date.now(), account_source: "blofin_disk" },
      });
      for (const c of sseClients) {
        try { c.write(`data: ${msg}\n\n`); } catch { sseClients.delete(c); }
      }
    } catch {
      // silently ignore poll errors
    }
  }, POLL_INTERVAL_MS);

  // Dashboard-Agent poller — reads Python agent log every 2s
  setInterval(() => {
    try {
      const logFile = path.join(OUTPUT_DIR, "dashboard_agent_log.jsonl");
      if (!fs.existsSync(logFile)) return;
      const lines = fs.readFileSync(logFile, "utf-8").split("\n").filter(Boolean);
      const last = lines.slice(-1)[0];
      if (!last) return;
      const entry = JSON.parse(last);
      const msg = JSON.stringify({
        type: "dashboard_agent",
        data: {
          status: entry.drift ? "active" : "idle",
          last_drift: entry.drift,
          llm_calls_this_window: 0,
          events_queued: (entry.events || []).length,
          drift_details: entry.details || [],
          corrections: entry.corrections || [],
        },
      });
      for (const c of sseClients) {
        try { c.write(`data: ${msg}\n\n`); } catch { sseClients.delete(c); }
      }
    } catch {
      // silently ignore
    }
  }, 2000);
}

const DASHBOARD_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OWL Swarm Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0a0f;--card:#12121a;--border:#1e1e2e;--text:#e0e0e0;--dim:#666;--accent:#7c3aed;--green:#10b981;--red:#ef4444;--yellow:#f59e0b;--blue:#3b82f6}
body{font-family:'SF Mono','Fira Code',Consolas,monospace;background:var(--bg);color:var(--text);min-height:100vh}
.header{background:linear-gradient(135deg,#1a0a2e,#0a0a0f);padding:20px 30px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:1.4em;background:linear-gradient(90deg,#7c3aed,#3b82f6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.status-badge{padding:6px 16px;border-radius:20px;font-size:0.85em;font-weight:600}
.status-running{background:rgba(16,185,129,0.15);color:var(--green);border:1px solid rgba(16,185,129,0.3)}
.status-stopped{background:rgba(239,68,68,0.15);color:var(--red);border:1px solid rgba(239,68,68,0.3)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;padding:20px 30px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px}
.card h3{font-size:0.75em;color:var(--dim);text-transform:uppercase;letter-spacing:1px;margin-bottom:12px}
.metric{font-size:1.8em;font-weight:700;margin:8px 0;transition:all 0.15s ease}
.metric.positive{color:var(--green)}.metric.negative{color:var(--red)}.metric.neutral{color:var(--blue)}
.row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:0.85em}
.row:last-child{border-bottom:none}
.row .label{color:var(--dim)}.row .value{font-weight:600}
.log{height:250px;overflow-y:auto;font-size:0.8em;line-height:1.6}
.log-entry{padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.02)}
.log-entry .time{color:var(--dim);margin-right:8px}
.log-entry.error .msg{color:var(--red)}
.log-entry.success .msg{color:var(--green)}
.log-entry.warn .msg{color:var(--yellow)}
.positions-table{width:100%;border-collapse:collapse;font-size:0.8em}
.positions-table th{text-align:left;padding:6px;color:var(--dim);border-bottom:1px solid var(--border);font-size:0.7em;text-transform:uppercase}
.positions-table td{padding:6px;border-bottom:1px solid rgba(255,255,255,0.02)}
.pnl-pos{color:var(--green)}.pnl-neg{color:var(--red)}
.full-width{grid-column:1/-1}
</style>
</head>
<body>
<div class="header">
  <div><h1>🦉 OWL SWARM</h1><div style="color:var(--dim);font-size:0.75em;margin-top:4px">Self-Verifying Agent Swarm — Blofin Perpetual Futures</div></div>
  <div style="display:flex;align-items:center;gap:16px">
    <span id="statusBadge" class="status-badge status-stopped">STOPPED</span>
    <span id="cycleCount" style="color:var(--dim);font-size:0.85em">Cycle: 0</span>
  </div>
</div>
<div class="grid">
  <div class="card"><h3>💰 Account Equity</h3><div id="equity" class="metric neutral">$0.00</div><div class="row"><span class="label">Available</span><span id="available" class="value">$0.00</span></div><div class="row"><span class="label">Total Trades</span><span id="totalTrades" class="value">0</span></div><div class="row"><span class="label">Open Positions</span><span id="posCount" class="value">0</span></div></div>
  <div class="card"><h3>📊 Open Positions</h3><div id="positionsContainer" style="max-height:200px;overflow-y:auto"><div style="color:var(--dim);text-align:center;padding:20px">No open positions</div></div></div>
  <div class="card"><h3>🤖 Agent Activity</h3><div class="row"><span class="label">Active Agents</span><span id="agentsActive" class="value">0</span></div><div class="row"><span class="label">Verification Pass</span><span id="verifyRate" class="value">100%</span></div><div class="row"><span class="label">Skills Learned</span><span id="skillsCount" class="value">0</span></div><div class="row"><span class="label">Constraints</span><span id="constraintsCount" class="value">0</span></div></div>
  <div class="card"><h3>📡 Dashboard-Agent</h3><div class="row"><span class="label">Status</span><span id="daStatus" class="value">idle</span></div><div class="row"><span class="label">Drift</span><span id="daDrift" class="value">none</span></div><div class="row"><span class="label">LLM Calls</span><span id="daLLM" class="value">0</span></div><div class="row"><span class="label">Events</span><span id="daEvents" class="value">0</span></div></div>
  <div class="card"><h3>📋 Recent Activity</h3><div id="tradeLog" class="log" style="height:250px"></div></div>
  <div class="card full-width"><h3>📜 Full Event Log</h3><div id="fullLog" class="log" style="height:400px"></div></div>
</div>
<script>
const fullLog = document.getElementById('fullLog');
const tradeLog = document.getElementById('tradeLog');

function addLog(msg, type, target){
  const el = target || fullLog;
  const d = document.createElement('div');
  d.className = 'log-entry' + (type ? ' ' + type : '');
  const t = new Date().toLocaleTimeString();
  d.innerHTML = '<span class="time">'+t+'</span><span class="msg">'+msg+'</span>';
  el.prepend(d);
  if(el.children.length > 300) el.lastChild.remove();
}

// Smooth number animation for all sliding values (equity, pnl, mark, roe)
let _slideState={};
let _slideRaf=0;
function _slideTo(key,target){
  if(!_slideState[key]) _slideState[key]={current:target,target:target};
  _slideState[key].target=target;
  if(!_slideRaf) _slideRaf=requestAnimationFrame(_slideTick);
}
function _slideTick(){
  let active=false;
  for(const k in _slideState){
    const s=_slideState[k];
    const diff=s.target-s.current;
    if(Math.abs(diff)>0.000001){
      s.current+=diff*0.2;
      active=true;
    } else {
      s.current=s.target;
    }
  }
  _slideUpdateDOM();
  if(active) _slideRaf=requestAnimationFrame(_slideTick);
  else _slideRaf=0;
}
function _slideUpdateDOM(){
  const eq=_slideState['equity']; if(eq){ const el=document.getElementById('equity'); if(el) el.textContent='$'+eq.current.toFixed(2); }
  const av=_slideState['available']; if(av){ const el=document.getElementById('available'); if(el) el.textContent='$'+av.current.toFixed(2); }
  for(const k in _slideState){
    if(k.startsWith('mark_') || k.startsWith('pnl_') || k.startsWith('roe_')){
      const el=document.getElementById(k);
      if(el){
        const s=_slideState[k];
        if(k.startsWith('mark_')) el.textContent=s.current.toFixed(4);
        else if(k.startsWith('pnl_')) el.textContent=(s.current>=0?'+':'')+s.current.toFixed(4);
        else if(k.startsWith('roe_')) el.textContent=(s.current>=0?'+':'')+s.current.toFixed(2)+'%';
      }
    }
  }
}

function setVal(id, v){
  const el = document.getElementById(id);
  if(el) el.textContent = v;
}

function updatePositions(positions){
  const c = document.getElementById('positionsContainer');
  if(!positions || positions.length === 0){
    c.innerHTML = '<div style="color:var(--dim);text-align:center;padding:20px">No open positions</div>';
    return;
  }
  let html = '<table class="positions-table"><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>Mark</th><th>P&L</th><th>ROE</th></tr>';
  for(const p of positions){
    const pnl = parseFloat(p.unrealizedPnl || 0);
    const cls = pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
    const side = parseFloat(p.positions) > 0 ? 'LONG' : 'SHORT';
    const roe = p.roe != null ? (p.roe >= 0 ? '+' : '') + p.roe.toFixed(2) + '%' : '';
    const inst = p.instId;
    _slideTo('mark_'+inst, parseFloat(p.markPrice||0));
    _slideTo('pnl_'+inst, pnl);
    _slideTo('roe_'+inst, p.roe || 0);
    html += '<tr><td>'+p.instId+'</td><td>'+side+'</td><td>'+Math.abs(parseFloat(p.positions)).toFixed(4)+'</td><td>'+parseFloat(p.averagePrice).toFixed(4)+'</td><td id="mark_'+inst+'">'+parseFloat(p.markPrice||0).toFixed(4)+'</td><td class="'+cls+'" id="pnl_'+inst+'">'+pnl.toFixed(4)+'</td><td id="roe_'+inst+'">'+roe+'</td></tr>';
  }
  html += '</table>';
  c.innerHTML = html;
  if(!_slideRaf) _slideRaf=requestAnimationFrame(_slideTick);
}

// Fetch initial status via API in case SSE missed updates
fetch('/api/status').then(r => r.json()).then(s => {
  setVal('cycleCount', 'Cycle: ' + s.cycleCount);
  _slideTo('equity', s.equity || 0);
  _slideTo('available', s.available || 0);
  setVal('totalTrades', s.totalTrades || 0);
  setVal('agentsActive', s.agentsActive || 0);
  setVal('verifyRate', (s.verificationPassRate || 100) + '%');
  setVal('skillsCount', s.skills || 0);
  setVal('constraintsCount', s.constraints || 0);
  setVal('posCount', (s.openPositions||[]).length);
  const badge = document.getElementById('statusBadge');
  if(s.running){ badge.className='status-badge status-running'; badge.textContent='● RUNNING'; }
  else { badge.className='status-badge status-stopped'; badge.textContent='■ STOPPED'; }
  updatePositions(s.openPositions);
}).catch(() => {});

const evtSource = new EventSource('/events');

evtSource.onmessage = function(e){
  try{
    const msg = JSON.parse(e.data);

    if(msg.type === 'status'){
      const s = msg.data;
      setVal('cycleCount', 'Cycle: ' + s.cycleCount);
      _slideTo('equity', s.equity || 0);
      _slideTo('available', s.available || 0);
      setVal('totalTrades', s.totalTrades || 0);
      setVal('agentsActive', s.agentsActive || 0);
      setVal('verifyRate', (s.verificationPassRate || 100) + '%');
      setVal('skillsCount', s.skills || 0);
      setVal('constraintsCount', s.constraints || 0);
      setVal('posCount', (s.openPositions||[]).length);

      const badge = document.getElementById('statusBadge');
      if(s.running){
        badge.className = 'status-badge status-running';
        badge.textContent = '● RUNNING';
      } else {
        badge.className = 'status-badge status-stopped';
        badge.textContent = '■ STOPPED';
      }
      if(s.lastError) addLog('ERROR: ' + s.lastError, 'error');
      updatePositions(s.openPositions);
    }

    // Live equity/positions update (every 500ms) — smooth slide
    if(msg.type === 'live'){
      const d = msg.data;
      _slideTo('equity', d.equity || 0);
      _slideTo('available', d.available || 0);
      setVal('posCount', (d.positions||[]).length);
      updatePositions(d.positions);
      // Color flash on equity change direction
      const eqEl = document.getElementById('equity');
      if(eqEl && window._prevEquity !== undefined){
        const pnl = (d.equity || 0) - window._prevEquity;
        if(Math.abs(pnl) > 0.001){
          eqEl.style.transition = 'color 0.15s';
          eqEl.style.color = pnl > 0 ? '#10b981' : '#ef4444';
          setTimeout(() => { eqEl.style.color = ''; }, 300);
        }
      }
      window._prevEquity = d.equity || 0;
    }

    // Dashboard-Agent status update
    if(msg.type === 'dashboard_agent'){
      const da = msg.data || {};
      setVal('daStatus', da.status || 'idle');
      setVal('daDrift', da.last_drift ? 'detected' : 'none');
      setVal('daLLM', da.llm_calls_this_window || 0);
      setVal('daEvents', da.events_queued || 0);
      const daStatusEl = document.getElementById('daStatus');
      if(daStatusEl){
        daStatusEl.style.color = da.status === 'active' ? '#10b981' : '#666';
      }
    }

    if(msg.type === 'log'){
      addLog(msg.message || msg.msg, msg.level || '');
    }

    if(msg.type === 'trade'){
      addLog('🟢 TRADE: ' + msg.data.side + ' ' + msg.data.instId + ' size=' + msg.data.size + ' @ ' + msg.data.entry, 'success');
    }

    if(msg.type === 'cycle'){
      addLog('✅ Cycle ' + msg.data.cycle + ' complete (' + (msg.data.duration/1000).toFixed(0) + 's) equity=$' + (msg.data.equity||0).toFixed(2), '');
    }

    if(msg.type === 'position_risk'){
      const d = msg.data;
      const adlFlag = d.adlRisk ? " ADL-RISK" : "";
      const liqP = (d.liquidationPrice||0).toFixed(2);
      const distP = (d.distancePct||0).toFixed(1);
      const marginP = (d.marginRatio||0).toFixed(2);
      const riskMsg = d.instId + ": liq=" + liqP + " dist=" + distP + "% margin=" + marginP + "%" + adlFlag;
      addLog(riskMsg, d.dangerLevel === 'critical' ? 'error' : 'warn');
    }

    if(!msg.type && msg.message){
      addLog(msg.message, msg.level || '');
    }

  }catch(err){ console.error('SSE parse error', err); }
};

evtSource.onerror = function(){
  console.warn('SSE connection lost, reconnecting...');
};
</script>
</body>
</html>`;
