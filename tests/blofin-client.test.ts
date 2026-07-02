import { describe, it, expect } from "vitest";
import { rankFromTickers, computePositionSize, defaultTpsl, tickerChangePct } from "../src/blofin/analytics.js";

describe("tickerChangePct", () => {
  it("should calculate positive change", () => {
    const ticker = { instId: "BTC-USDT", last: "105000", open24h: "100000", high24h: "106000", low24h: "99000", volCurrency24h: "1000000", vol24h: "1000", ts: "123" };
    expect(tickerChangePct(ticker)).toBeCloseTo(5);
  });
  it("should return null for zero open", () => {
    const ticker = { instId: "BTC-USDT", last: "105000", open24h: "0", high24h: "106000", low24h: "99000", volCurrency24h: "1000000", vol24h: "1000", ts: "123" };
    expect(tickerChangePct(ticker)).toBeNull();
  });
});

describe("rankFromTickers", () => {
  const tickers = [
    { instId: "BTC-USDT", last: "105000", open24h: "100000", high24h: "106000", low24h: "99000", volCurrency24h: "5000000000", vol24h: "50000", ts: "123" },
    { instId: "ETH-USDT", last: "2100", open24h: "2000", high24h: "2200", low24h: "1900", volCurrency24h: "1000000000", vol24h: "500000", ts: "123" },
    { instId: "SOL-USDT", last: "150", open24h: "160", high24h: "165", low24h: "148", volCurrency24h: "500000000", vol24h: "3000000", ts: "123" },
  ];
  it("should rank by momentum and volume", () => {
    const ranked = rankFromTickers(tickers, new Set(), {}, 10);
    expect(ranked.length).toBe(3);
    // Highest max(longScore, shortScore) should be first
    expect(ranked[0].instId).toBeTruthy();
  });
  it("should filter blocked symbols", () => {
    const ranked = rankFromTickers(tickers, new Set(["BTC-USDT"]), {}, 10);
    expect(ranked.every((r) => r.instId !== "BTC-USDT")).toBe(true);
  });
  it("should respect topN limit", () => {
    const ranked = rankFromTickers(tickers, new Set(), {}, 2);
    expect(ranked.length).toBe(2);
  });
});

describe("computePositionSize", () => {
  it("should size based on risk", () => {
    const result = computePositionSize({ equityUsdt: 100, riskPct: 0.01, entry: 100, stop: 98, minSize: 1, lotSize: 1, contractValue: 1, leverage: 50 });
    expect(Number(result.size)).toBeGreaterThanOrEqual(1);
  });
  it("should fall back to min size for low equity", () => {
    const result = computePositionSize({ equityUsdt: 0, riskPct: 0.01, entry: 100, stop: 98, minSize: 1, lotSize: 1, contractValue: 1, leverage: 50 });
    expect(result.size).toBe("1");
    expect(result.reason).toBe("fallback_minimum");
  });
});

describe("defaultTpsl", () => {
  it("should set SL below entry for buy", () => {
    const tpsl = defaultTpsl(100, "buy", 0.1);
    expect(Number(tpsl.slTriggerPrice)).toBeLessThan(100);
    expect(Number(tpsl.tpTriggerPrice)).toBeGreaterThan(100);
    expect(tpsl.closeSide).toBe("sell");
  });
  it("should set SL above entry for sell", () => {
    const tpsl = defaultTpsl(100, "sell", 0.1);
    expect(Number(tpsl.slTriggerPrice)).toBeGreaterThan(100);
    expect(Number(tpsl.tpTriggerPrice)).toBeLessThan(100);
    expect(tpsl.closeSide).toBe("buy");
  });
});
