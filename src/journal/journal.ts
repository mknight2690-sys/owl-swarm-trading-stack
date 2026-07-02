/** Persistent trade journal — ported from Python trade_journal.py */

import fs from "node:fs";
import path from "node:path";

const OUTPUT_DIR = process.env["OUTPUT_DIR"] ?? "outputs";
const JOURNAL_PATH = path.join(OUTPUT_DIR, "trade_journal.jsonl");
const POSITION_SNAPSHOT_PATH = path.join(OUTPUT_DIR, "position_snapshot.json");

fs.mkdirSync(OUTPUT_DIR, { recursive: true });

export interface JournalEvent {
  ts: number;
  type: string;
  [key: string]: unknown;
}

export interface SymbolStats {
  trades: number;
  wins: number;
  losses: number;
  blocked: number;
  totalPnl: number;
  lastPnl: number;
}

let statsCache: { ts: number; stats: Record<string, SymbolStats> } | null = null;

function ensureParent(): void {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

export function recordEvent(event: Record<string, unknown>): void {
  ensureParent();
  const row: JournalEvent = { ts: Date.now(), ...event } as JournalEvent;
  fs.appendFileSync(JOURNAL_PATH, JSON.stringify(row) + "\n");
  statsCache = null;
}

export function loadEvents(limit = 500): JournalEvent[] {
  if (!fs.existsSync(JOURNAL_PATH)) return [];
  const content = fs.readFileSync(JOURNAL_PATH, "utf-8");
  const lines = content.trim().split("\n").filter(Boolean);
  const events: JournalEvent[] = [];
  const start = Math.max(0, lines.length - limit);
  for (let i = start; i < lines.length; i++) {
    try { events.push(JSON.parse(lines[i])); } catch { /* skip */ }
  }
  return events;
}

export function symbolStats(): Record<string, SymbolStats> {
  const now = Date.now();
  if (statsCache && now - statsCache.ts < 5000) return statsCache.stats;
  const stats: Record<string, SymbolStats> = {};
  for (const ev of loadEvents(500)) {
    const inst = ev.instId as string;
    if (!inst) continue;
    const bucket: SymbolStats = stats[inst] ?? { trades: 0, wins: 0, losses: 0, blocked: 0, totalPnl: 0, lastPnl: 0 };
    const etype = ev.type as string;
    if (etype === "order_placed") bucket.trades++;
    else if (etype === "order_blocked") bucket.blocked++;
    else if (etype === "position_closed") {
      const pnl = Number(ev.realizedPnl ?? 0);
      bucket.totalPnl += pnl;
      bucket.lastPnl = pnl;
      if (pnl > 0) bucket.wins++;
      else if (pnl < 0) bucket.losses++;
    }
    stats[inst] = bucket;
  }
  statsCache = { ts: now, stats };
  return stats;
}

export interface PositionSnapshot {
  [instId: string]: {
    instId: string;
    positions: string;
    side: string;
    averagePrice: string;
    markPrice: string;
    unrealizedPnl: string;
  };
}

export function syncPositionCloses(currentPositions: Array<{ instId: string; positions: string; averagePrice: string; markPrice: string; unrealizedPnl: string }>): void {
  const current: PositionSnapshot = {};
  for (const row of currentPositions) {
    if (!row.instId || Math.abs(Number(row.positions)) < 1e-12) continue;
    current[row.instId] = {
      instId: row.instId, positions: row.positions,
      side: Number(row.positions) > 0 ? "long" : "short",
      averagePrice: row.averagePrice, markPrice: row.markPrice, unrealizedPnl: row.unrealizedPnl,
    };
  }
  let previous: PositionSnapshot = {};
  try {
    if (fs.existsSync(POSITION_SNAPSHOT_PATH)) {
      previous = JSON.parse(fs.readFileSync(POSITION_SNAPSHOT_PATH, "utf-8"));
    }
  } catch { /* empty */ }
  for (const [inst, prev] of Object.entries(previous)) {
    if (!current[inst]) {
      recordEvent({
        type: "position_closed", instId: inst,
        realizedPnl: prev.unrealizedPnl, lastUnrealizedPnl: prev.unrealizedPnl,
        averagePrice: prev.averagePrice,
      });
    }
  }
  fs.writeFileSync(POSITION_SNAPSHOT_PATH, JSON.stringify(current));
}

export function insightsText(maxSymbols = 8): string {
  const stats = symbolStats();
  const events = loadEvents(20);
  if (Object.keys(stats).length === 0 && events.length === 0) {
    return "No trade history yet — first cycles are exploration.";
  }
  const lines = ["TRADE LEARNING (from past loop cycles):"];
  const ranked = Object.entries(stats).sort((a, b) => (b[1].wins - b[1].losses) - (a[1].wins - a[1].losses) || b[1].totalPnl - a[1].totalPnl);
  if (ranked.length > 0) {
    lines.push("Top symbols (wins - losses, total realized PnL):");
    for (const [inst, s] of ranked.slice(0, maxSymbols)) {
      lines.push(`  ${inst}: trades=${s.trades} W/L=${s.wins}/${s.losses} pnl=${s.totalPnl.toFixed(4)} blocked=${s.blocked}`);
    }
    const losers = [...ranked].sort((a, b) => (b[1].losses - b[1].wins) - (a[1].losses - a[1].wins));
    const avoid = losers.filter(([, s]) => s.losses > s.wins).map(([i]) => i).slice(0, 5);
    if (avoid.length > 0) lines.push(`Prefer to avoid (poor track record): ${avoid.join(", ")}`);
  }
  const recent = events.filter((e) => ["order_placed", "order_blocked", "position_closed"].includes(e.type as string));
  if (recent.length > 0) {
    lines.push("Recent events:");
    for (const ev of recent.slice(-5)) {
      lines.push(`  ${ev.type} ${ev.instId ?? ""} ${ev.side ?? ""} pnl=${ev.realizedPnl ?? ""}`);
    }
  }
  lines.push("Use this history: favor symbols with positive track record; skip repeat losers; never add to blocked open positions.");
  return lines.join("\n");
}
