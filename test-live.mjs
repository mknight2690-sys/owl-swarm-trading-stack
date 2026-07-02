/** Live connectivity + test trade via Python bridge */

import { writeFileSync, unlinkSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";
import { BlofinClient } from "./dist/blofin/client.js";
import { loadCredentials } from "./dist/blofin/credentials.js";
import { rankFromTickers } from "./dist/blofin/analytics.js";
import "dotenv/config";

const creds = loadCredentials();
const blofin = new BlofinClient(creds);
const PYTHON_EXE = "C:\\Users\\mknig\\AppData\\Local\\Programs\\Python\\Python312\\python.exe";
const BRIDGE_DIR = process.cwd();

function bridge(method, args) {
  const d = mkdtempSync(join(tmpdir(), "owl-"));
  const f = join(d, "args.json");
  writeFileSync(f, JSON.stringify(args));
  const p = spawn(PYTHON_EXE, ["blofin_bridge.py", method, `@${f}`], {
    cwd: BRIDGE_DIR,
    env: { ...process.env },
    timeout: 30000,
  });
  let stdout = "", stderr = "";
  p.stdout.on("data", d => stdout += d);
  p.stderr.on("data", d => stderr += d);
  return new Promise((resolve, reject) => {
    p.on("close", code => {
      try { unlinkSync(f); } catch (e) {}
      try { unlinkSync(d); } catch (e) {}
      if (code !== 0 && stdout.trim()) {
        try {
          const parsed = JSON.parse(stdout.trim());
          if (parsed.error) { reject(new Error(parsed.error)); return; }
          resolve(parsed); return;
        } catch (e) {}
      }
      if (code !== 0) { reject(new Error(stderr || `exit ${code}`)); return; }
      try { resolve(JSON.parse(stdout.trim())); }
      catch { resolve(stdout.trim()); }
    });
  });
}

console.log("=== LIVE CONNECTIVITY TEST ===");

// 1. Balance
console.log("\n--- 1: Account Balance ---");
const balance = await blofin.getBalances();
const equity = Number(balance.totalEquity ?? 0);
const available = Number(balance.details?.[0]?.availableEquity ?? 0);
console.log(`Equity: $${equity.toFixed(4)} | Available: $${available.toFixed(4)}`);

// 2. Positions
console.log("\n--- 2: Open Positions ---");
const positions = await blofin.getPositions();
console.log(`Open: ${positions.length}`);
positions.forEach(p => console.log(`  ${p.instId}: ${p.positions} @ ${p.averagePrice}`));

// 3. Tickers
console.log("\n--- 3: Tickers ---");
const tickers = await blofin.getTickers();
console.log(`Tickers: ${tickers.length}`);

// 4. Rank
console.log("\n--- 4: Opportunities ---");
const ranked = rankFromTickers(tickers, new Set(), {}, 10);
ranked.forEach(r => console.log(`  ${r.instId}: $${r.last} chg=${r.chgPct24h}% side=${r.suggestedSide}`));

// 5. Find affordable instrument
console.log("\n--- 5: Finding affordable instrument ---");
let tradeCandidate = null;
for (const r of ranked.slice(0, 20)) {
  try {
    const inst = await blofin.getInstrument(r.instId);
    if (!inst) continue;
    const price = Number(r.last);
    const contractValue = Number(inst.contractValue ?? 1);
    const minSize = Number(inst.minSize);
    const notional = price * contractValue * minSize;
    console.log(`  ${r.instId}: price=$${price} cv=${contractValue} min=${minSize} notional=$${notional.toFixed(2)} side=${r.suggestedSide}`);
    if (notional <= available * 0.5 && r.suggestedSide !== "neutral") {
      tradeCandidate = { ...r, inst };
      console.log(`  >>> SELECTED: ${r.instId}`);
      break;
    }
  } catch (e) { /* skip */ }
}

if (!tradeCandidate) {
  console.log("No affordable instrument found. Trying DOGE-USDT...");
  // Find DOGE
  const doge = tickers.find(t => t.instId === "DOGE-USDT" || t.instId === "DOGE-USDT-SWAP");
  if (doge) {
    const inst = await blofin.getInstrument(doge.instId);
    tradeCandidate = { ...doge, inst, suggestedSide: "long", chgPct24h: 0, longScore: 0.5, shortScore: 0.5 };
  }
}

if (tradeCandidate) {
  const { instId, last, suggestedSide } = tradeCandidate;
  const inst = tradeCandidate.inst;
  const minSize = Number(inst.minSize);
  const tickSize = Number(inst.tickSize);
  const contractValue = Number(inst.contractValue ?? 1);
  const maxLeverage = Number(inst.maxLeverage ?? 50);
  const leverage = Math.min(20, maxLeverage);  // conservative
  const price = Number(last);
  const side = suggestedSide === "long" ? "buy" : "sell";
  const slPct = 0.015;
  const tpPct = 0.025;
  const sl = side === "buy" ? price * (1 - slPct) : price * (1 + slPct);
  const tp = side === "buy" ? price * (1 + tpPct) : price * (1 - tpPct);
  const roundT = (v, t) => {
    if (!t || t <= 0) return v.toFixed(4);
    const r = Math.round(v / t) * t;
    const d = String(t).split(".")[1]?.replace(/0+$/, "").length ?? 4;
    return r.toFixed(d);
  };
  const notional = price * contractValue * minSize;
  console.log(`\n--- 6: TEST TRADE on ${instId} ---`);
  console.log(`Side: ${side} | Size: ${minSize} | Entry: $${price}`);
  console.log(`SL: $${roundT(sl, tickSize)} | TP: $${roundT(tp, tickSize)}`);
  console.log(`Notional: $${notional.toFixed(4)} | Leverage: ${leverage}x`);
  console.log(`Contract value: ${contractValue} | Tick: ${tickSize}`);

  try {
    console.log("\nSetting leverage...");
    await blofin.setLeverage(instId, leverage);
    console.log("Leverage OK");

    console.log("Placing market order with TP/SL...");
    const order = await blofin.placeOrder({
      instId, side, orderType: "market", size: String(minSize),
      tpTriggerPrice: roundT(tp, tickSize),
      slTriggerPrice: roundT(sl, tickSize),
    });
    console.log("ORDER RESULT:", JSON.stringify(order));

    // Verify
    const newPos = await blofin.getPositions(instId);
    if (newPos.length > 0) {
      console.log("POSITION CONFIRMED:", JSON.stringify(newPos[0]));
    }
    console.log("\n=== TEST TRADE SUCCESSFUL ===");
  } catch (err) {
    console.error("TRADE FAILED:", err.message);
  }
} else {
  console.log("No suitable instrument found for test trade");
}

console.log("\n=== DONE ===");
