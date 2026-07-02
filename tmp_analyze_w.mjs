import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import {
  parseCandles,
  technicalAnalysis,
  fundingBias,
  orderBookImbalance,
  tickerChangePct,
} from "./dist/blofin/analytics.js";

const PY = "C:\\Users\\mknig\\AppData\\Local\\Programs\\Python\\Python312\\python.exe";
const BRIDGE = "blofin_bridge.py";
const CWD = "C:\\Users\\mknig\\owl-swarm";
const INST = "W-USDT";

function bridge(method, args) {
  const argsFile = `${CWD}\\tmp_bridge_args.json`;
  writeFileSync(argsFile, JSON.stringify(args));
  const r = spawnSync(PY, [BRIDGE, method, `@${argsFile}`], { cwd: CWD, encoding: "utf8" });
  const out = (r.stdout || "").trim();
  if (r.status !== 0) {
    throw new Error(`${method} failed: ${r.stderr || out}`);
  }
  const jsonStart = out.search(/[\[{]/);
  return JSON.parse(out.slice(jsonStart >= 0 ? jsonStart : 0));
}

const tickerArr = bridge("get_ticker", { inst_id: INST });
const ticker = Array.isArray(tickerArr) ? tickerArr[0] : tickerArr;
const c15Raw = bridge("get_candles", { inst_id: INST, bar: "15m", limit: 100 });
const c1hRaw = bridge("get_candles", { inst_id: INST, bar: "1h", limit: 48 });
const funding = bridge("get_funding_rate", { inst_id: INST });
const book = bridge("get_order_book", { inst_id: INST, size: "20" });

const candles = parseCandles(c15Raw);
const candles1h = parseCandles(c1hRaw);
const fundingRate = Number(funding.fundingRate);
const ta = technicalAnalysis(candles, fundingRate);
const fb = fundingBias(fundingRate);
const ob = orderBookImbalance(book);

const price = Number(ticker.last);
const change24h = tickerChangePct(ticker) ?? 0;
const volume24h = Number(ticker.volCurrency24h ?? ticker.vol24h);
const low24 = Number(ticker.low24h);
const high24 = Number(ticker.high24h);

const recent20 = candles.slice(-20);
const support15 = Math.min(...recent20.map((c) => c.low));
const resistance15 = Math.max(...recent20.map((c) => c.high));
const resistance1h = Math.max(...candles1h.slice(-6).map((c) => c.high));
const support1h = Math.min(...candles1h.slice(-6).map((c) => c.low));

let trend = "neutral";
if (ta.ema9 != null && ta.ema21 != null) {
  if (ta.ema9 > ta.ema21 && price > ta.ema21) trend = "bullish";
  else if (ta.ema9 < ta.ema21 && price < ta.ema21) trend = "bearish";
  else if (ta.ema9 > ta.ema21) trend = "bullish_pullback";
  else trend = "bearish_bounce";
}

const mom1h =
  candles.length >= 5
    ? ((candles.at(-1).close - candles.at(-5).close) / candles.at(-5).close) * 100
    : 0;
const mom6h =
  candles.length >= 25
    ? ((candles.at(-1).close - candles.at(-25).close) / candles.at(-25).close) * 100
    : 0;

let confidence = ta.technicalScore;
if (change24h > 40) confidence *= 0.88;
if (ta.rsi14 != null && ta.rsi14 > 70) confidence *= 0.82;
if (ta.rsi14 != null && ta.rsi14 > 75) confidence *= 0.9;
if (fb.bias === "crowded_long" || fb.bias === "mild_long_crowding") confidence *= 0.93;
if (price >= high24 * 0.98) confidence *= 0.9;
if (ob.imbalance > 0.08) confidence = Math.min(1, confidence + 0.04);
if (ob.imbalance < -0.08) confidence = Math.max(0, confidence - 0.04);
confidence = Math.round(Math.max(0, Math.min(1, confidence)) * 1000) / 1000;

const side =
  ta.suggestedBias === "long"
    ? "long"
    : ta.suggestedBias === "short"
      ? "short"
      : change24h > 0
        ? "long"
        : "short";

const report = {
  instId: INST,
  price,
  change24h: Math.round(change24h * 1000) / 1000,
  volume24h,
  trend,
  momentumScore: ta.momentumScore,
  keyLevels: [ta.keyLevels.support, ta.keyLevels.pivot, ta.keyLevels.resistance],
  fundingRate,
  fundingBias: fb.bias,
  technicalSummary: [
    `Price ${price.toFixed(5)} after +${change24h.toFixed(1)}% 24h; EMA9 ${ta.ema9?.toFixed(5) ?? "n/a"} vs EMA21 ${ta.ema21?.toFixed(5) ?? "n/a"} — ${trend.replace(/_/g, " ")} on 15m.`,
    `RSI(14)=${ta.rsi14 ?? "n/a"}; 1h mom ${mom1h.toFixed(2)}%, 6h mom ${mom6h.toFixed(2)}%; ATR vol ${ta.volatilityPct}%.`,
    `Key zone: support ${support15.toFixed(5)} (15m) / ${support1h.toFixed(5)} (1h); resistance ${resistance15.toFixed(5)} (15m) / ${resistance1h.toFixed(5)} (1h). 24h range ${low24}–${high24}.`,
    `Funding ${(fundingRate * 100).toFixed(4)}% (${fb.bias.replace(/_/g, " ")}); order book imbalance ${ob.imbalance} (bid ${(ob.bidPct * 100).toFixed(1)}%).`,
  ].join(" "),
  ...(confidence >= 0.5 ? { suggestedSide: side } : {}),
  confidence,
};

console.log(JSON.stringify(report));
