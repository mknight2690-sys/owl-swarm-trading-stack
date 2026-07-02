/**
 * Advanced Blofin Analytics — Funding, ADL, Tiers, Liquidation, Fees
 * Research-backed edge cases for perpetual futures trading.
 */

import type { Ticker, Instrument, Position, Candle, FundingRate } from "./types.js";

// ─── Funding Rate Intelligence ──────────────────────────────────────────────

export interface FundingInfo {
  rate: string;
  bias: "long-heavy" | "short-heavy" | "neutral";
  absRate: number;
  annualizedCostPct: number;  // cost per year if held
  nextFundingTs: number;      // UTC timestamp of next settlement
  shouldAvoidLong: boolean;
  shouldAvoidShort: boolean;
}

/**
 * Analyze funding rate for a position.
 * Positive rate = longs pay shorts → avoid longs when rate is high
 * Negative rate = shorts pay longs → avoid shorts when rate is very negative
 */
export function analyzeFunding(funding: FundingRate | null, markPrice = 0): FundingInfo {
  if (!funding) {
    return { rate: "0", bias: "neutral", absRate: 0, annualizedCostPct: 0, nextFundingTs: 0, shouldAvoidLong: false, shouldAvoidShort: false };
  }

  const rate = Number(funding.fundingRate ?? 0);
  const absRate = Math.abs(rate);

  // Annualized: 3 settlements per day × 365 days
  const annualizedCostPct = absRate * 3 * 365 * 100;

  let bias: FundingInfo["bias"] = "neutral";
  if (rate > 0.001) bias = "long-heavy";
  else if (rate < -0.001) bias = "short-heavy";

  // Next settlement: Blofin pays every 8h at 00:00, 08:00, 16:00 UTC
  const now = Date.now();
  const utcHour = new Date().getUTCHours();
  // Find next settlement hour
  const settlementHours = [0, 8, 16];
  let nextHour = 0;
  let dayOffset = 0;
  for (const h of settlementHours) {
    if (utcHour < h) { nextHour = h; break; }
    nextHour = h; // keep last match
  }
  if (utcHour >= 16) { nextHour = 0; dayOffset = 1; } // wrap to tomorrow 00:00
  const nextFundingDate = new Date();
  nextFundingDate.setUTCDate(nextFundingDate.getUTCDate() + dayOffset);
  nextFundingDate.setUTCHours(nextHour, 0, 0, 0);
  const nextFundingTs = nextFundingDate.getTime();

  // Avoid thresholds: > 0.05% per 8h (0.15%/day, ~55%/yr) is expensive
  // Rate is decimal: 0.0005 = 0.05%
  const shouldAvoidLong = rate > 0.0005;   // >0.05% per 8h → >~55%/yr
  const shouldAvoidShort = rate < -0.0005; // <-0.05% per 8h → >~55%/yr cost for shorts

  return {
    rate: funding.fundingRate,
    bias,
    absRate,
    annualizedCostPct,
    nextFundingTs,
    shouldAvoidLong,
    shouldAvoidShort,
  };
}

/**
 * Estimate funding cost for holding a position over N hours.
 */
export function estimateFundingCost(notionalUsd: number, fundingRateStr: number, hours: number): number {
  const settlements = (hours / 8);
  return notionalUsd * fundingRateStr * settlements;
}

// ─── Position Tier Intelligence ─────────────────────────────────────────────

export interface TierInfo {
  maxLeverage: number;
  maintenanceMarginRatio: number;
  minSize: number;
  maxSize: number;
  // At what notional does this tier kick in?
  minNotional: number;
  maxNotional: number;
}

/**
 * Blofin USDT cross-margin tiers (as of 2026).
 * These change periodically — the system fetches live tiers via API.
 * This is a fallback/default table.
 */
const DEFAULT_TIERS: TierInfo[] = [
  { maxLeverage: 150, maintenanceMarginRatio: 0.0067, minSize: 0, maxSize: Infinity, minNotional: 0, maxNotional: 5000 },
  { maxLeverage: 125, maintenanceMarginRatio: 0.008,  minSize: 0, maxSize: Infinity, minNotional: 5000, maxNotional: 25000 },
  { maxLeverage: 100, maintenanceMarginRatio: 0.01,   minSize: 0, maxSize: Infinity, minNotional: 25000, maxNotional: 100000 },
  { maxLeverage: 75,  maintenanceMarginRatio: 0.02,   minSize: 0, maxSize: Infinity, minNotional: 100000, maxNotional: 500000 },
  { maxLeverage: 50,  maintenanceMarginRatio: 0.03,   minSize: 0, maxSize: Infinity, minNotional: 500000, maxNotional: 1000000 },
  { maxLeverage: 20,  maintenanceMarginRatio: 0.05,   minSize: 0, maxSize: Infinity, minNotional: 1000000, maxNotional: 10000000 },
  { maxLeverage: 10,  maintenanceMarginRatio: 0.1,    minSize: 0, maxSize: Infinity, minNotional: 10000000, maxNotional: Infinity },
];

/**
 * Get the tier for a given notional value.
 * Used for position sizing and leverage selection.
 */
export function getTierForNotional(notionalUsd: number, tiers: TierInfo[] = DEFAULT_TIERS): TierInfo {
  for (const tier of tiers) {
    if (notionalUsd >= tier.minNotional && notionalUsd < tier.maxNotional) {
      return tier;
    }
  }
  return tiers[tiers.length - 1]; // fallback to lowest tier
}

/**
 * Calculate the maximum safe leverage for a position given account equity,
 * risk tolerance, and instrument tier limits.
 */
export function safeLeverage(
  notionalUsd: number,
  accountEquity: number,
  riskPct: number = 0.01,
  tiers: TierInfo[] = DEFAULT_TIERS,
): number {
  const tier = getTierForNotional(notionalUsd, tiers);
  // Max leverage based on risk: riskPct / (maintenanceMarginRatio + buffer)
  const mmBuffer = tier.maintenanceMarginRatio + 0.02; // 2% safety buffer
  const riskBasedLeverage = riskPct / mmBuffer;
  return Math.min(tier.maxLeverage, Math.floor(riskBasedLeverage));
}

// ─── Liquidation Price Estimation ───────────────────────────────────────────

export interface LiquidationInfo {
  markPrice: number;
  liquidationPrice: number;
  marginRatio: number;
  distanceToLiquidationPct: number;
  dangerLevel: "safe" | "warning" | "danger" | "critical";
  adlRisk: boolean;
}

/**
 * Estimate liquidation price for a long position using mark price.
 * Blofin uses mark price for liquidation, not last price.
 * Formula (cross margin, long):
 *   liqPrice = markPrice × (1 - (available + unrealizedPnl) / (|size| × markPrice))
 */
export function estimateLiquidationLong(markPrice: number, size: number, availableMargin: number, unrealizedPnl: number = 0): number {
  const totalEquity = availableMargin + unrealizedPnl;
  const notional = Math.abs(size) * markPrice;
  if (notional <= 0) return 0;
  return markPrice * (1 - totalEquity / notional);
}

/**
 * Estimate liquidation price for a short position.
 */
export function estimateLiquidationShort(markPrice: number, size: number, availableMargin: number, unrealizedPnl: number = 0): number {
  const totalEquity = availableMargin + unrealizedPnl;
  const notional = Math.abs(size) * markPrice;
  if (notional <= 0) return Infinity;
  return markPrice * (1 + totalEquity / notional);
}

/**
 * Analyze a position's liquidation risk.
 */
export function analyzeLiquidationRisk(pos: Position, accountAvailable: number): LiquidationInfo {
  const size = Number(pos.positions);
  const mark = Number(pos.markPrice || 0);
  const avgPrice = Number(pos.averagePrice || 0);
  const unrealizedPnl = Number(pos.unrealizedPnl || 0);
  // Blofin returns marginRatio as decimal (e.g. "0.5" = 50%)
  const marginRatio = Number(pos.marginRatio || 0);

  if (mark <= 0) {
    return { markPrice: 0, liquidationPrice: 0, marginRatio, distanceToLiquidationPct: 100, dangerLevel: "safe", adlRisk: false };
  }

  let liqPrice: number;
  if (size > 0) {
    liqPrice = estimateLiquidationLong(mark, size, accountAvailable, unrealizedPnl);
  } else {
    liqPrice = estimateLiquidationShort(mark, size, accountAvailable, unrealizedPnl);
  }

  // Distance from current price to liquidation price
  let distancePct: number;
  if (size > 0) {
    distancePct = ((mark - liqPrice) / mark) * 100;
  } else {
    distancePct = ((liqPrice - mark) / mark) * 100;
  }

  let dangerLevel: LiquidationInfo["dangerLevel"] = "safe";
  if (distancePct < 2) dangerLevel = "critical";
  else if (distancePct < 5) dangerLevel = "danger";
  else if (distancePct < 10) dangerLevel = "warning";

  // ADL risk: high margin ratio + profitable position = likely ADL target
  const adlRisk = marginRatio > 0.5 && unrealizedPnl > 0;

  return {
    markPrice: mark,
    liquidationPrice: liqPrice,
    marginRatio,
    distanceToLiquidationPct: distancePct,
    dangerLevel,
    adlRisk,
  };
}

// ─── Fee Intelligence ───────────────────────────────────────────────────────

export interface FeeEstimate {
  makerFeePct: number;
  takerFeePct: number;
  entryFeeUsd: number;
  exitFeeUsd: number;
  totalRoundTripFeeUsd: number;
  totalRoundTripFeePct: number;
}

// Default VIP 0 rates
const MAKER_PCT = 0.0002;  // 0.02%
const TAKER_PCT = 0.0006;  // 0.06%

export function estimateFees(notionalUsd: number, isMarketOrder = true): FeeEstimate {
  const rate = isMarketOrder ? TAKER_PCT : MAKER_PCT;
  const entryFee = notionalUsd * rate;
  const exitFee = notionalUsd * rate;
  const total = entryFee + exitFee;
  return {
    makerFeePct: MAKER_PCT,
    takerFeePct: TAKER_PCT,
    entryFeeUsd: entryFee,
    exitFeeUsd: exitFee,
    totalRoundTripFeeUsd: total,
    totalRoundTripFeePct: total / notionalUsd * 100,
  };
}

// ─── Spread & Liquidity Analysis ────────────────────────────────────────────

export interface LiquidityInfo {
  spreadPct: number;
  bidDepthUsd: number;
  askDepthUsd: number;
  slippageEstimatePct: number;
  isLiquidEnough: boolean;
  recommendation: string;
}

/**
 * Analyze if an instrument is liquid enough for a given position size.
 */
export function analyzeLiquidity(
  ticker: Ticker | undefined,
  orderBook?: { bids: [string, string][]; asks: [string, string][] },
  targetNotionalUsd: number = 0,
): LiquidityInfo {
  if (!ticker) {
    return { spreadPct: 100, bidDepthUsd: 0, askDepthUsd: 0, slippageEstimatePct: 100, isLiquidEnough: false, recommendation: "No ticker data" };
  }
  const bidPrice = Number(ticker.bidPrice || 0);
  const askPrice = Number(ticker.askPrice || 0);
  const lastPrice = Number(ticker.last || 0);

  // If bid/ask are available, use them. Otherwise estimate spread from 24h volume.
  let spreadPct: number;
  let midPrice: number;
  if (bidPrice > 0 && askPrice > 0) {
    midPrice = (bidPrice + askPrice) / 2;
    spreadPct = ((askPrice - bidPrice) / midPrice) * 100;
    // Sanity check: if spread is absurdly wide (>5%), the ticker data is stale — use volume proxy
    if (spreadPct > 5) {
      const vol24h = Number(ticker.volCurrency24h || 0);
      if (vol24h > 5000000) spreadPct = 0.15;
      else if (vol24h > 1000000) spreadPct = 0.3;
      else if (vol24h > 100000) spreadPct = 0.5;
      else spreadPct = 1.0;
    }
  } else if (lastPrice > 0) {
    // No bid/ask in ticker — estimate spread based on 24h volume
    // Higher volume = tighter spread. Use volCurrency24h as proxy.
    const vol24h = Number(ticker.volCurrency24h || 0);
    midPrice = lastPrice;
    // Estimate: >$1M daily vol ≈ 0.1% spread, >$100K ≈ 0.3%, >$10K ≈ 0.5%, else 1%
    if (vol24h > 1000000) spreadPct = 0.1;
    else if (vol24h > 100000) spreadPct = 0.3;
    else if (vol24h > 10000) spreadPct = 0.5;
    else spreadPct = 1.0;
  } else {
    midPrice = 0;
    spreadPct = 100;
  }

  // Estimate slippage based on spread
  let slippageEstimatePct = spreadPct / 2; // base slippage is half spread

  // If we have order book data, calculate depth-based slippage
  let bidDepthUsd = 0;
  let askDepthUsd = 0;
  if (orderBook) {
    for (const [p, sz] of orderBook.bids.slice(0, 20)) {
      bidDepthUsd += Number(p) * Number(sz);
    }
    for (const [p, sz] of orderBook.asks.slice(0, 20)) {
      askDepthUsd += Number(p) * Number(sz);
    }
    // Slippage = how much of the book our order eats
    if (targetNotionalUsd > 0) {
      const depth = targetNotionalUsd > 0 ? Math.min(bidDepthUsd, askDepthUsd) : 0;
      if (depth > 0 && targetNotionalUsd > depth) {
        slippageEstimatePct = Math.max(slippageEstimatePct, (targetNotionalUsd / depth) * spreadPct);
      }
    }
  }

  // If we have order book data, check depth. Otherwise rely on spread + volume proxy.
  const hasOrderBook = orderBook && (orderBook.bids.length > 0 || orderBook.asks.length > 0);
  const depthOk = !hasOrderBook || Math.min(bidDepthUsd, askDepthUsd) > targetNotionalUsd;
  // Spread < 1.5% is acceptable; volume proxy already implies liquid market
  const isLiquidEnough = spreadPct < 1.5 && depthOk;

  let recommendation = "OK";
  if (spreadPct > 3) recommendation = "WIDE SPREAD — avoid";
  else if (spreadPct > 1.5) recommendation = "Moderate spread — reduce size";
  else if (!isLiquidEnough && targetNotionalUsd > 0) recommendation = "Low depth — reduce size";

  return { spreadPct, bidDepthUsd, askDepthUsd, slippageEstimatePct, isLiquidEnough, recommendation };
}

// ─── Multi-Timeframe Analysis ───────────────────────────────────────────────

export interface MultiTimeframeSignal {
  shortTerm: "bullish" | "bearish" | "neutral";   // 1m-5m
  mediumTerm: "bullish" | "bearish" | "neutral";  // 15m-1h
  longTerm: "bullish" | "bearish" | "neutral";    // 4h+
  consensus: "long" | "short" | "neutral";
  confidence: number; // 0-1
}

/**
 * Analyze multiple timeframes for a consensus signal.
 * Uses EMA crossovers and momentum.
 */
export function multiTimeframeAnalysis(
  candles1m: Candle[],
  candles15m: Candle[],
  candles1h: Candle[],
): MultiTimeframeSignal {
  const closes1m = candles1m.map(c => Number(c.close));
  const closes15m = candles15m.map(c => Number(c.close));
  const closes1h = candles1h.map(c => Number(c.close));

  // Short term: 5m EMA vs 20m EMA
  const shortEma5 = ema(closes1m, 5);
  const shortEma20 = ema(closes1m, 20);
  const shortTerm = shortEma5 > shortEma20 ? "bullish" : shortEma5 < shortEma20 ? "bearish" : "neutral";

  // Medium term: 15m EMA 10 vs 30
  const medEma10 = ema(closes15m, 10);
  const medEma30 = ema(closes15m, 30);
  const mediumTerm = medEma10 > medEma30 ? "bullish" : medEma10 < medEma30 ? "bearish" : "neutral";

  // Long term: 1h EMA 12 vs 26
  const longEma12 = ema(closes1h, 12);
  const longEma26 = ema(closes1h, 26);
  const longTerm = longEma12 > longEma26 ? "bullish" : longEma12 < longEma26 ? "bearish" : "neutral";

  // Consensus
  const bullishCount = [shortTerm, mediumTerm, longTerm].filter(t => t === "bullish").length;
  const bearishCount = [shortTerm, mediumTerm, longTerm].filter(t => t === "bearish").length;

  let consensus: MultiTimeframeSignal["consensus"] = "neutral";
  if (bullishCount >= 2) consensus = "long";
  else if (bearishCount >= 2) consensus = "short";

  const confidence = consensus === "neutral" ? 0.3 : (Math.max(bullishCount, bearishCount) / 3);

  return { shortTerm, mediumTerm, longTerm, consensus, confidence };
}

function ema(values: number[], period: number): number {
  if (values.length < period) return values[values.length - 1] || 0;
  const k = 2 / (period + 1);
  let e = values[0];
  for (let i = 1; i < values.length; i++) {
    e = values[i] * k + e * (1 - k);
  }
  return e;
}

// ─── Comprehensive Opportunity Scoring ──────────────────────────────────────

export interface EnhancedOpportunity {
  instId: string;
  ticker: Ticker;
  funding: FundingInfo | null;
  liquidity: LiquidityInfo;
  technical: {
    trend: string;
    momentumScore: number;
    rsi: number;
    atr: number;
    bollinger: { upper: number; mid: number; lower: number };
  };
  compositeScore: number; // 0-100
  reasons: string[];
  avoidReasons: string[];
}

/**
 * Score an opportunity using ALL available data.
 * This is the main entry point for the research agent.
 */
export function scoreOpportunity(
  ticker: Ticker,
  funding: FundingRate | null,
  candles1m: Candle[],
  candles15m: Candle[],
  candles1h: Candle[],
  orderBook?: { bids: [string, string][]; asks: [string, string][] },
): EnhancedOpportunity {
  const instId = ticker.instId;
  const reasons: string[] = [];
  const avoidReasons: string[] = [];
  let score = 50; // start neutral

  // 1. Funding analysis
  const fundingInfo = analyzeFunding(funding);
  if (fundingInfo.shouldAvoidLong) {
    score -= 15;
    avoidReasons.push(`High funding cost: ${(fundingInfo.annualizedCostPct).toFixed(1)}%/yr`);
  } else if (fundingInfo.shouldAvoidShort) {
    score -= 15;
    avoidReasons.push(`Negative funding: ${(fundingInfo.annualizedCostPct).toFixed(1)}%/yr`);
  } else if (fundingInfo.absRate < 0.0001) {
    score += 5;
    reasons.push("Low funding cost");
  }

  // 2. Liquidity analysis
  const liquidity = analyzeLiquidity(ticker, orderBook);
  if (!liquidity.isLiquidEnough) {
    score -= 20;
    avoidReasons.push(`Low liquidity: spread=${liquidity.spreadPct.toFixed(3)}%`);
  } else if (liquidity.spreadPct < 0.05) {
    score += 10;
    reasons.push("Excellent liquidity");
  }

  // 3. Technical analysis
  const closes1m = candles1m.map(c => Number(c.close));
  const closes15m = candles15m.map(c => Number(c.close));
  const closes1h = candles1h.map(c => Number(c.close));

  const rsi = closes1m.length >= 15 ? computeRsi(closes1m, 14) : 50;
  const atr = candles1m.length >= 14 ? computeAtr(candles1m, 14) : 0;
  const ema5 = closes1m.length >= 5 ? ema(closes1m, 5) : 0;
  const ema20 = closes1m.length >= 20 ? ema(closes1m, 20) : 0;

  let trend = "neutral";
  if (ema5 > ema20 * 1.002) { trend = "bullish"; score += 10; reasons.push("EMA bullish cross"); }
  else if (ema5 < ema20 * 0.998) { trend = "bearish"; score -= 10; avoidReasons.push("EMA bearish cross"); }

  // RSI
  if (rsi > 70) { score -= 10; avoidReasons.push(`RSI overbought: ${rsi.toFixed(0)}`); }
  else if (rsi < 30) { score -= 5; avoidReasons.push(`RSI oversold: ${rsi.toFixed(0)}`); }
  else if (rsi > 50) { score += 5; reasons.push("RSI bullish"); }
  else { score -= 3; }

  // Momentum from 15m
  if (closes15m.length >= 2) {
    const change15m = (closes15m[closes15m.length - 1] - closes15m[0]) / closes15m[0] * 100;
    if (Math.abs(change15m) > 2) {
      score += change15m > 0 ? 10 : -10;
      reasons.push(`15m momentum: ${change15m > 0 ? '+' : ''}${change15m.toFixed(2)}%`);
    }
  }

  // Volume
  const vol = Number(ticker.volCurrency24h || 0);
  if (vol > 1000000) { score += 5; reasons.push("High volume"); }
  else if (vol < 10000) { score -= 10; avoidReasons.push("Low volume"); }

  // Clamp
  score = Math.max(0, Math.min(100, score));

  return {
    instId,
    ticker,
    funding: fundingInfo,
    liquidity,
    technical: { trend, momentumScore: score, rsi, atr, bollinger: { upper: 0, mid: 0, lower: 0 } },
    compositeScore: score,
    reasons,
    avoidReasons,
  };
}

function computeRsi(closes: number[], period: number): number {
  if (closes.length < period + 1) return 50;
  let gains = 0, losses = 0;
  for (let i = closes.length - period; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) gains += diff;
    else losses -= diff;
  }
  const avgGain = gains / period;
  const avgLoss = losses / period;
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

function computeAtr(candles: Candle[], period: number): number {
  if (candles.length < period + 1) return 0;
  let trSum = 0;
  for (let i = candles.length - period; i < candles.length; i++) {
    const high = Number(candles[i].high);
    const low = Number(candles[i].low);
    const prevClose = Number(candles[i - 1].close);
    const tr = Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose));
    trSum += tr;
  }
  return trSum / period;
}
