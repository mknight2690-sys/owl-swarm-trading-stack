/** Technical analysis and opportunity ranking — ported from Python market_analytics.py */

import type { Ticker, Candle } from "./types.js";

function f(value: unknown, defaultValue = 0): number {
  const n = Number(value);
  return isNaN(n) ? defaultValue : n;
}

export function parseCandles(raw: unknown[][]): Candle[] {
  const out: Candle[] = [];
  for (const row of raw) {
    if (!row || row.length < 5) continue;
    out.push({
      ts: f(row[0]), open: f(row[1]), high: f(row[2]),
      low: f(row[3]), close: f(row[4]), volume: f(row[5]),
    });
  }
  return out.reverse();
}

export function ema(values: number[], period: number): number | null {
  if (values.length < period || period < 1) return null;
  const k = 2 / (period + 1);
  let val = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < values.length; i++) {
    val = values[i] * k + val * (1 - k);
  }
  return val;
}

export function rsi(closes: number[], period = 14): number | null {
  if (closes.length < period + 1) return null;
  const gains: number[] = [];
  const losses: number[] = [];
  for (let i = 1; i < closes.length; i++) {
    const delta = closes[i] - closes[i - 1];
    gains.push(Math.max(delta, 0));
    losses.push(Math.max(-delta, 0));
  }
  const avgGain = gains.slice(-period).reduce((a, b) => a + b, 0) / period;
  const avgLoss = losses.slice(-period).reduce((a, b) => a + b, 0) / period;
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

export function atr(candles: Candle[], period = 14): number | null {
  if (candles.length < period + 1) return null;
  const trs: number[] = [];
  for (let i = 1; i < candles.length; i++) {
    const { high, low } = candles[i];
    const prevClose = candles[i - 1].close;
    trs.push(Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose)));
  }
  return trs.slice(-period).reduce((a, b) => a + b, 0) / period;
}

export function bollinger(closes: number[], period = 20, mult = 2): { middle: number; upper: number; lower: number } | null {
  if (closes.length < period) return null;
  const window = closes.slice(-period);
  const mid = window.reduce((a, b) => a + b, 0) / period;
  const variance = window.reduce((sum, x) => sum + (x - mid) ** 2, 0) / period;
  const std = Math.sqrt(variance);
  return { middle: mid, upper: mid + mult * std, lower: mid - mult * std };
}

export function fundingBias(fundingRate: number): { bias: string; sentimentScore: number; note: string } {
  if (fundingRate > 0.0003) return { bias: "crowded_long", sentimentScore: 0.35, note: "High positive funding — longs pay shorts; fade risk on longs." };
  if (fundingRate > 0.0001) return { bias: "mild_long_crowding", sentimentScore: 0.45, note: "Mild long crowding." };
  if (fundingRate < -0.0003) return { bias: "crowded_short", sentimentScore: 0.65, note: "High negative funding — shorts pay longs; squeeze risk on shorts." };
  if (fundingRate < -0.0001) return { bias: "mild_short_crowding", sentimentScore: 0.55, note: "Mild short crowding." };
  return { bias: "neutral", sentimentScore: 0.5, note: "Funding near neutral." };
}

export function orderBookImbalance(book: { bids: [string, string][]; asks: [string, string][] }): { bidPct: number; askPct: number; imbalance: number } {
  const bidVol = book.bids.slice(0, 10).reduce((s, b) => s + f(b[1]), 0);
  const askVol = book.asks.slice(0, 10).reduce((s, a) => s + f(a[1]), 0);
  const total = bidVol + askVol;
  if (total <= 0) return { bidPct: 0.5, askPct: 0.5, imbalance: 0 };
  const bidPct = bidVol / total;
  return { bidPct: Math.round(bidPct * 10000) / 10000, askPct: Math.round((1 - bidPct) * 10000) / 10000, imbalance: Math.round((bidPct - 0.5) * 10000) / 10000 };
}

export interface TechnicalAnalysis {
  last: number;
  ema9: number | null;
  ema21: number | null;
  ema50: number | null;
  rsi14: number | null;
  atr14: number | null;
  volatilityPct: number;
  bollinger: { middle: number; upper: number; lower: number } | null;
  trendStrength: number;
  momentumScore: number;
  technicalScore: number;
  shortScore: number;
  keyLevels: { support: number; resistance: number; pivot: number };
  suggestedBias: string;
  source?: string;
  warning?: string;
}

export function technicalAnalysis(candles: Candle[], fundingRate?: number): TechnicalAnalysis {
  const closes = candles.map((c) => c.close);
  if (closes.length < 20) return { last: closes[0] ?? 0, ema9: null, ema21: null, ema50: null, rsi14: null, atr14: null, volatilityPct: 0, bollinger: null, trendStrength: 0.5, momentumScore: 0.5, technicalScore: 0.5, shortScore: 0.5, keyLevels: { support: 0, resistance: 0, pivot: 0 }, suggestedBias: "neutral", error: "insufficient_candles" } as unknown as TechnicalAnalysis;
  const last = closes[closes.length - 1];
  const ema9 = ema(closes, 9);
  const ema21 = ema(closes, 21);
  const ema50 = closes.length >= 50 ? ema(closes, 50) : null;
  const rsi14 = rsi(closes, 14);
  const atr14 = atr(candles, 14);
  const bb = bollinger(closes, 20);
  let trend = 0.5;
  if (ema9 !== null && ema21 !== null) {
    if (ema9 > ema21 && last > ema21) trend = 0.75;
    else if (ema9 < ema21 && last < ema21) trend = 0.25;
    else if (ema9 > ema21) trend = 0.6;
    else trend = 0.4;
  }
  let momentum = 0.5;
  if (rsi14 !== null) {
    if (rsi14 > 70) momentum = 0.3;
    else if (rsi14 > 55) momentum = 0.65;
    else if (rsi14 < 30) momentum = 0.7;
    else if (rsi14 < 45) momentum = 0.35;
  }
  const volPct = atr14 && last > 0 ? (atr14 / last) * 100 : 0;
  const support = Math.min(...candles.slice(-20).map((c) => c.low));
  const resistance = Math.max(...candles.slice(-20).map((c) => c.high));
  const pivot = (support + resistance + last) / 3;
  let longScore = trend * 0.4 + momentum * 0.35;
  if (fundingRate !== undefined) {
    const fb = fundingBias(fundingRate);
    longScore = longScore * 0.85 + fb.sentimentScore * 0.15;
  }
  return {
    last, ema9, ema21, ema50,
    rsi14: rsi14 !== null ? Math.round(rsi14 * 100) / 100 : null,
    atr14: atr14 !== null ? Math.round(atr14 * 1e6) / 1e6 : null,
    volatilityPct: Math.round(volPct * 1000) / 1000,
    bollinger: bb,
    trendStrength: Math.round(trend * 1000) / 1000,
    momentumScore: Math.round(momentum * 1000) / 1000,
    technicalScore: Math.round(longScore * 1000) / 1000,
    shortScore: Math.round((1 - longScore) * 1000) / 1000,
    keyLevels: { support: Math.round(support * 1e8) / 1e8, resistance: Math.round(resistance * 1e8) / 1e8, pivot: Math.round(pivot * 1e8) / 1e8 },
    suggestedBias: longScore >= 0.55 ? "long" : longScore <= 0.45 ? "short" : "neutral",
  };
}

export function tickerProxyAnalysis(ticker: Ticker, fundingRate?: number): TechnicalAnalysis {
  const last = f(ticker.last);
  if (last <= 0) return { last: 0, ema9: null, ema21: null, ema50: null, rsi14: null, atr14: null, volatilityPct: 0, bollinger: null, trendStrength: 0.5, momentumScore: 0.5, technicalScore: 0.5, shortScore: 0.5, keyLevels: { support: 0, resistance: 0, pivot: 0 }, suggestedBias: "neutral", source: "ticker_proxy_waf_fallback", error: "no_price" } as unknown as TechnicalAnalysis;
  const chg = tickerChangePct(ticker) ?? 0;
  const momentum = Math.max(0, Math.min(1, 0.5 + chg / 20));
  let trend = 0.5;
  if (chg > 1.5) trend = 0.65;
  else if (chg > 0.5) trend = 0.58;
  else if (chg < -1.5) trend = 0.35;
  else if (chg < -0.5) trend = 0.42;
  let longScore = trend * 0.5 + momentum * 0.5;
  if (fundingRate !== undefined) {
    const fb = fundingBias(fundingRate);
    longScore = longScore * 0.85 + fb.sentimentScore * 0.15;
  }
  const shortScore = 1 - longScore;
  const band = Math.max(0.01, Math.abs(chg) / 100 * 2);
  return {
    last, ema9: null, ema21: null, ema50: null, rsi14: null, atr14: null,
    volatilityPct: Math.round(Math.min(8, Math.abs(chg) / 2) * 1000) / 1000,
    bollinger: null,
    trendStrength: Math.round(trend * 1000) / 1000,
    momentumScore: Math.round(momentum * 1000) / 1000,
    technicalScore: Math.round(longScore * 1000) / 1000,
    shortScore: Math.round(shortScore * 1000) / 1000,
    keyLevels: {
      support: Math.round(last * (1 - band) * 1e8) / 1e8,
      resistance: Math.round(last * (1 + band) * 1e8) / 1e8,
      pivot: Math.round(last * 1e8) / 1e8,
    },
    suggestedBias: longScore >= 0.55 ? "long" : longScore <= 0.45 ? "short" : "neutral",
    source: "ticker_proxy_waf_fallback",
    warning: "Candle data unavailable (WAF); 24h ticker proxy only.",
  };
}

export function tickerChangePct(row: Ticker): number | null {
  const last = f(row.last);
  const open24 = f(row.open24h);
  if (open24 <= 0) return null;
  return (last - open24) / open24 * 100;
}

export interface RankedOpportunity {
  instId: string;
  last: string;
  chgPct24h: number;
  volCurrency24h: number;
  longScore: number;
  shortScore: number;
  journalWins: number;
  journalLosses: number;
  suggestedSide: string;
}

export function rankFromTickers(
  tickers: Ticker[],
  blocked: Set<string> = new Set(),
  journalStats: Record<string, { wins: number; losses: number; blocked: number }> = {},
  topN = 15
): RankedOpportunity[] {
  const ranked: RankedOpportunity[] = [];
  for (const row of tickers) {
    const inst = row.instId;
    if (!inst || blocked.has(inst) || !inst.endsWith("-USDT")) continue;
    const lastPrice = f(row.last);
    if (lastPrice <= 0) continue; // skip delisted/inactive pairs
    const chg = tickerChangePct(row);
    if (chg === null) continue;
    const vol = f(row.volCurrency24h);
    if (vol <= 0) continue;
    const momentumScore = Math.max(0, Math.min(1, 0.5 + chg / 20));
    const volumeScore = Math.max(0, Math.min(1, Math.log10(vol + 1) / 8));
    const journal = journalStats[inst] ?? { wins: 0, losses: 0, blocked: 0 };
    let journalScore = 0.5;
    if (journal.wins + journal.losses > 0) journalScore = journal.wins / (journal.wins + journal.losses);
    else if (journal.blocked > 2) journalScore = 0.2;
    const longScore = momentumScore * 0.45 + volumeScore * 0.35 + journalScore * 0.2;
    const shortScore = (1 - momentumScore) * 0.45 + volumeScore * 0.35 + (1 - journalScore) * 0.2;
    ranked.push({
      instId: inst, last: row.last, chgPct24h: Math.round(chg * 1000) / 1000,
      volCurrency24h: vol, longScore: Math.round(longScore * 1000) / 1000,
      shortScore: Math.round(shortScore * 1000) / 1000,
      journalWins: journal.wins, journalLosses: journal.losses,
      suggestedSide: longScore >= shortScore ? "long" : "short",
    });
  }
  ranked.sort((a, b) => Math.max(b.longScore, b.shortScore) - Math.max(a.longScore, a.shortScore));
  return ranked.slice(0, topN);
}

export interface PositionSizeResult {
  size: string;
  riskUsdt: number;
  notionalUsdt: number;
  marginAt50xUsdt: number;
  equityUsdt: number;
  riskPct: number;
  reason: string;
}

export function computePositionSize(params: {
  equityUsdt: number;
  riskPct: number;
  entry: number;
  stop: number;
  minSize: number;
  lotSize: number;
  contractValue?: number;
  leverage?: number;
}): PositionSizeResult {
  const { equityUsdt, riskPct, entry, stop, minSize, lotSize, contractValue = 1, leverage = 50 } = params;
  if (!isFinite(equityUsdt) || equityUsdt <= 0 || !isFinite(entry) || entry <= 0 || !isFinite(minSize) || minSize <= 0) {
    return { size: String(minSize), riskUsdt: 0, notionalUsdt: 0, marginAt50xUsdt: 0, equityUsdt, riskPct, reason: "fallback_minimum" };
  }
  const riskAmount = equityUsdt * Math.max(0.005, Math.min(riskPct, 0.05));
  const stopDist = Math.abs(entry - stop);
  if (stopDist <= 0) {
    return { size: String(minSize), riskUsdt: 0, notionalUsdt: 0, marginAt50xUsdt: 0, equityUsdt, riskPct, reason: "zero_stop_distance" };
  }
  let rawSize = riskAmount / stopDist;
  if (lotSize > 0) rawSize = Math.floor(rawSize / lotSize) * lotSize;
  const size = Math.max(minSize, rawSize);
  const notional = size * contractValue * entry;
  const marginAt50x = notional / leverage;
  return {
    size: String(size), riskUsdt: Math.round(riskAmount * 1e4) / 1e4,
    notionalUsdt: Math.round(notional * 100) / 100,
    marginAt50xUsdt: Math.round(marginAt50x * 1e6) / 1e6,
    equityUsdt: Math.round(equityUsdt * 1e4) / 1e4,
    riskPct, reason: "risk_based",
  };
}

export function defaultTpsl(entryPrice: number, side: string, tick = 0.1, slPct = 0.015, tpPct = 0.025): {
  closeSide: string; slTriggerPrice: string; slOrderPrice: string; slTriggerPriceType: string;
  tpTriggerPrice: string; tpOrderPrice: string; tpTriggerPriceType: string;
} {
  const sideL = side.toLowerCase();
  let sl: number, tp: number, closeSide: string;
  if (sideL === "buy") {
    sl = entryPrice * (1 - slPct);
    tp = entryPrice * (1 + tpPct);
    closeSide = "sell";
  } else {
    sl = entryPrice * (1 + slPct);
    tp = entryPrice * (1 - tpPct);
    closeSide = "buy";
  }
  const roundToTick = (v: number) => {
    if (tick <= 0) return v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
    const rounded = Math.round(Math.round(v / tick) * tick * 1e10) / 1e10;
    const decimals = Math.max(0, String(tick).split(".")[1]?.replace(/0+$/, "").length ?? 0);
    return rounded.toFixed(decimals);
  };
  return {
    closeSide,
    slTriggerPrice: roundToTick(sl), slOrderPrice: "-1", slTriggerPriceType: "last",
    tpTriggerPrice: roundToTick(tp), tpOrderPrice: "-1", tpTriggerPriceType: "last",
  };
}
