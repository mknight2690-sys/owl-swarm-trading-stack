import { spawnSync } from "child_process";
import { parseCandles, technicalAnalysis, fundingBias, orderBookImbalance, tickerChangePct } from "./dist/blofin/analytics.js";

const py = "C:\\Users\\mknig\\AppData\\Local\\Programs\\Python\\Python312\\python.exe";
const cwd = "C:\\Users\\mknig\\owl-swarm";

function bridgeFile(method, file) {
  const r = spawnSync(py, ["blofin_bridge.py", method, `@${file}`], { cwd, encoding: "utf8" });
  const s = r.stdout.trim();
  const obj = s.lastIndexOf("{");
  const arr = s.indexOf("[");
  const i = obj >= 0 && (arr < 0 || obj < arr) ? obj : arr;
  return JSON.parse(s.slice(i));
}

const funding = bridgeFile("get_funding_rate", `${cwd}\\tmp_saga_funding.json`);
const book = bridgeFile("get_order_book", `${cwd}\\tmp_saga_book.json`);
const c1m = bridgeFile("get_candles", `${cwd}\\tmp_saga_1m.json`);
const c15 = bridgeFile("get_candles", `${cwd}\\tmp_saga_15m.json`);
const c1h = bridgeFile("get_candles", `${cwd}\\tmp_saga_1h.json`);
const tickerRaw = bridgeFile("get_ticker", `${cwd}\\tmp_saga_ticker.json`);
const ticker = Array.isArray(tickerRaw) ? tickerRaw[0] : tickerRaw;

const fr = Number(funding.fundingRate);
const fb = fundingBias(fr);
const ob = orderBookImbalance(book);
const bid = Number(book.bids[0][0]);
const ask = Number(book.asks[0][0]);
const spreadPct = ((ask - bid) / ((ask + bid) / 2)) * 100;

const candles1m = parseCandles(c1m);
const candles15 = parseCandles(c15);
const candles1h = parseCandles(c1h);
const ta1m = technicalAnalysis(candles1m, fr);
const ta15 = technicalAnalysis(candles15, fr);
const ta1h = technicalAnalysis(candles1h, fr);

const price = Number(ticker.last);
const change24h = tickerChangePct(ticker);
const volume24h = Number(ticker.volCurrency24h);
const low24 = Number(ticker.low24h);
const high24 = Number(ticker.high24h);

const support = Math.min(ta15.keyLevels.support, ta1h.keyLevels.support, low24);
const resistance = Math.max(ta15.keyLevels.resistance, ta1h.keyLevels.resistance);
const pivot = (high24 + low24 + price) / 3;

let trend = "neutral";
const alignedBull = ta1m.suggestedBias === "long" && ta15.suggestedBias === "long" && ta1h.suggestedBias === "long";
const alignedBear = ta1m.suggestedBias === "short" && ta15.suggestedBias === "short" && ta1h.suggestedBias === "short";
if (alignedBull) trend = "bullish";
else if (alignedBear) trend = "bearish";
else if (ta1h.suggestedBias === "long" && ta1m.suggestedBias === "long") trend = "bullish_pullback";
else if (ta1h.suggestedBias === "short") trend = "bearish";
else trend = "mixed";

const momentumScore = Math.round(((ta1m.momentumScore + ta15.momentumScore + ta1h.momentumScore) / 3) * 1000) / 1000;

let confidence = ta1m.technicalScore * 0.35 + ta15.technicalScore * 0.35 + ta1h.technicalScore * 0.3;
if (spreadPct > 0.5) confidence -= 0.25;
if (fr > 0.005) confidence -= 0.2;
if (fr < -0.005) confidence -= 0.2;
if (alignedBull || alignedBear) confidence += 0.08;
else confidence -= 0.1;
if (change24h > 10) confidence += 0.05;
if (ta1m.rsi14 > 70) confidence -= 0.05;
confidence = Math.max(0, Math.min(1, Math.round(confidence * 1000) / 1000));

let suggestedSide = confidence >= 0.5 ? (ta1m.technicalScore >= ta15.technicalScore ? ta1m.suggestedBias : ta15.suggestedBias) : "neutral";
if (suggestedSide === "neutral" && confidence >= 0.5) suggestedSide = change24h > 0 ? "long" : "short";

const technicalSummary = [
  `1m RSI ${ta1m.rsi14} trend ${ta1m.suggestedBias}; 15m RSI ${ta15.rsi14} trend ${ta15.suggestedBias}; 1h RSI ${ta1h.rsi14} trend ${ta1h.suggestedBias}.`,
  `24h +${change24h.toFixed(2)}% from ${Number(ticker.open24h)}; pullback from high ${high24} to ${price}.`,
  `Funding ${fr.toExponential(2)} (${fb.bias}); spread ${spreadPct.toFixed(3)}%; book imbalance ${ob.imbalance}.`,
  alignedBull || alignedBear ? "Multi-timeframe aligned." : "Timeframes mixed — partial pullback within 24h uptrend.",
].join(" ");

console.log(JSON.stringify({
  instId: "SAGA-USDT",
  price,
  change24h: Math.round(change24h * 1000) / 1000,
  volume24h,
  trend,
  momentumScore,
  keyLevels: [Math.round(support * 1e5) / 1e5, Math.round(pivot * 1e5) / 1e5, Math.round(resistance * 1e5) / 1e5],
  fundingRate: fr,
  fundingBias: fb.bias,
  spreadPct: Math.round(spreadPct * 10000) / 10000,
  technicalSummary,
  suggestedSide: confidence >= 0.5 ? suggestedSide : "neutral",
  confidence,
}));
