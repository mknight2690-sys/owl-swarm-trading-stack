import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { parseCandles, technicalAnalysis, fundingBias, orderBookImbalance, ema, rsi } from "./dist/blofin/analytics.js";

const PY = "C:\\Users\\mknig\\AppData\\Local\\Programs\\Python\\Python312\\python.exe";
const BRIDGE = "blofin_bridge.py";
const CWD = "C:\\Users\\mknig\\owl-swarm";
const INST = "CLO-USDT";
const ARGS_FILE = `${CWD}\\tmp_bridge_args.json`;

function bridge(method, args) {
  writeFileSync(ARGS_FILE, JSON.stringify(args));
  const r = spawnSync(PY, [BRIDGE, method, `@${ARGS_FILE}`], { cwd: CWD, encoding: "utf8" });
  if (r.status !== 0) {
    console.error(r.stderr || r.stdout);
    process.exit(1);
  }
  const out = r.stdout.trim();
  const jsonStart = out.indexOf(out.startsWith("[") ? "[" : "{");
  return JSON.parse(out.slice(jsonStart >= 0 ? jsonStart : 0));
}

const tickerArr = bridge("get_ticker", { inst_id: INST });
const ticker = Array.isArray(tickerArr) ? tickerArr[0] : tickerArr;
const funding = bridge("get_funding_rate", { inst_id: INST });
const book = bridge("get_order_book", { inst_id: INST, size: "20" });
const candles1mRaw = bridge("get_candles", { inst_id: INST, bar: "1m", limit: "50" });
const candles15mRaw = bridge("get_candles", { inst_id: INST, bar: "15m", limit: "30" });
const candles1hRaw = bridge("get_candles", { inst_id: INST, bar: "1H", limit: "24" });

const candles1m = parseCandles(candles1mRaw);
const candles15m = parseCandles(candles15mRaw);
const candles1h = parseCandles(candles1hRaw);
const fundingRate = Number(funding.fundingRate);
const fb = fundingBias(fundingRate);
const ob = orderBookImbalance(book);

const bestBid = Number(book.bids?.[0]?.[0] ?? 0);
const bestAsk = Number(book.asks?.[0]?.[0] ?? 0);
const mid = bestBid && bestAsk ? (bestBid + bestAsk) / 2 : Number(ticker.last);
const spreadPct = mid > 0 ? ((bestAsk - bestBid) / mid) * 100 : 999;

const ta1m = technicalAnalysis(candles1m, fundingRate);
const ta15 = technicalAnalysis(candles15m, fundingRate);
const ta1h = technicalAnalysis(candles1h, fundingRate);

const last = Number(ticker.last);
const open24 = Number(ticker.open24h);
const change24h = ticker.chg_pct != null ? Number(ticker.chg_pct) : ((last - open24) / open24) * 100;
const volume24h = Number(ticker.volCurrency24h ?? ticker.vol24h);

function tfTrend(ta) {
  if (ta.ema9 != null && ta.ema21 != null) {
    if (ta.ema9 > ta.ema21 && ta.last > ta.ema21) return "bearish";
    if (ta.ema9 < ta.ema21 && ta.last < ta.ema21) return "bearish";
    if (ta.ema9 > ta.ema21) return "bullish_pullback";
    return "bearish_bounce";
  }
  return ta.trendStrength >= 0.55 ? "bullish" : ta.trendStrength <= 0.45 ? "bearish" : "neutral";
}

function tfDir(ta) {
  if (ta.suggestedBias === "long") return 1;
  if (ta.suggestedBias === "short") return -1;
  return 0;
}

const trend1m = ta1m.trendStrength >= 0.55 ? "bullish" : ta1m.trendStrength <= 0.45 ? "bearish" : "neutral";
const trend15 = ta15.trendStrength >= 0.55 ? "bullish" : ta15.trendStrength <= 0.45 ? "bearish" : "neutral";
const trend1h = ta1h.trendStrength >= 0.55 ? "bullish" : ta1h.trendStrength <= 0.45 ? "bearish" : "neutral";

const alignment = [tfDir(ta1m), tfDir(ta15), tfDir(ta1h)];
const bearishCount = alignment.filter((d) => d === -1).length;
const bullishCount = alignment.filter((d) => d === 1).length;

let trend = "neutral";
if (bearishCount >= 2) trend = "bearish";
else if (bullishCount >= 2) trend = "bullish";
else trend = "mixed";

let suggestedSide = "neutral";
let confidence = 0;

const avoidLongFunding = fundingRate > 0.005;
const avoidShortFunding = fundingRate < -0.005;
const avoidSpread = spreadPct > 0.5;

if (!avoidSpread) {
  let base = (ta15.shortScore + ta1h.shortScore + (1 - ta1m.momentumScore)) / 3;
  if (change24h < -20) base = Math.min(1, base + 0.08);
  if (bearishCount >= 2) base = Math.min(1, base + 0.1);
  if (bullishCount >= 2) base = Math.max(0, base - 0.15);
  if (ta1m.rsi14 != null && ta1m.rsi14 < 30) base = Math.min(1, base + 0.05);
  if (ta1m.rsi14 != null && ta1m.rsi14 > 70) base = Math.min(1, base + 0.03);
  if (fb.bias === "crowded_long") base = Math.min(1, base + 0.02);
  if (ob.imbalance < -0.1) base = Math.min(1, base + 0.03);
  if (avoidLongFunding && bearishCount < 3) base *= 0.9;

  const shortConf = base;
  const longConf = 1 - base;

  if (shortConf >= longConf && shortConf >= 0.5 && !avoidShortFunding) {
    suggestedSide = "short";
    confidence = shortConf;
  } else if (longConf > shortConf && longConf >= 0.5 && !avoidLongFunding) {
    suggestedSide = "long";
    confidence = longConf;
  } else {
    suggestedSide = shortConf > longConf ? "short" : "long";
    confidence = Math.max(shortConf, longConf);
  }
}

if (avoidSpread) {
  suggestedSide = "neutral";
  confidence = 0.2;
}

const keyLevels = [
  ta15.keyLevels.support,
  ta15.keyLevels.pivot,
  ta15.keyLevels.resistance,
];

const technicalSummary = [
  `24h ${change24h.toFixed(2)}% crash on ${(volume24h / 1e6).toFixed(2)}M USDT vol; live ${last}.`,
  `Spread ${spreadPct.toFixed(3)}%${avoidSpread ? " (AVOID)" : ""}; funding ${(fundingRate * 100).toFixed(4)}% (${fb.bias}).`,
  `1m RSI=${ta1m.rsi14} trend=${trend1m}; 15m RSI=${ta15.rsi14} momentum=${ta15.momentumScore}; 1h trendStrength=${ta1h.trendStrength} (${trend1h}).`,
  `MTF alignment: 1m/15m/1h ${alignment.map((d) => (d === 1 ? "L" : d === -1 ? "S" : "N")).join("/")}; book imbalance ${ob.imbalance}.`,
].join(" ");

const report = {
  instId: INST,
  price: last,
  change24h: Math.round(change24h * 1000) / 1000,
  volume24h,
  trend,
  momentumScore: ta15.momentumScore,
  keyLevels,
  fundingRate,
  fundingBias: fb.bias,
  spreadPct: Math.round(spreadPct * 10000) / 10000,
  technicalSummary,
  suggestedSide: confidence >= 0.5 ? suggestedSide : "neutral",
  confidence: Math.round(confidence * 1000) / 1000,
};

console.log(JSON.stringify(report));
