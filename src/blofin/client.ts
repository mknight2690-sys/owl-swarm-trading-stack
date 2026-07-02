/**
 * Blofin API Client
 * Routes all requests through the Python bridge (curl_cffi) for Cloudflare WAF bypass.
 */

import { callPythonBridge } from "./python-bridge.js";
import type {
  Ticker, Instrument, Position, Balance, OrderResult,
  TpslOrder, Candle, FundingRate, OrderBook, BlofinApiResponse,
} from "./types.js";
import type { BlofinCredentials } from "./types.js";

export class BlofinClient {
  constructor(_credentials: BlofinCredentials) {
    // Credentials are handled by the Python bridge
  }

  async getTickers(instType = "SWAP"): Promise<Ticker[]> {
    const result = await callPythonBridge("get_tickers", { inst_type: instType }) as Ticker[];
    return result ?? [];
  }

  async getTicker(instId: string): Promise<Ticker | null> {
    const result = await callPythonBridge("get_ticker", { inst_id: instId }) as Ticker;
    return result ?? null;
  }

  async getInstruments(instType = "SWAP"): Promise<Instrument[]> {
    const result = await callPythonBridge("get_instruments", { inst_type: instType }) as Instrument[];
    return result ?? [];
  }

  async getInstrument(instId: string): Promise<Instrument | null> {
    const result = await callPythonBridge("get_instrument", { inst_id: instId }) as Instrument;
    return result ?? null;
  }

  async getCandles(instId: string, bar = "1m", limit = 100): Promise<Candle[]> {
    const result = await callPythonBridge("get_candles", { inst_id: instId, bar, limit: String(limit) }) as Candle[];
    return result ?? [];
  }

  async getBalances(): Promise<Balance> {
    const result = await callPythonBridge("get_balances", {}) as Balance;
    return (result ?? {}) as Balance;
  }

  async getPositions(instId?: string): Promise<Position[]> {
    const args: Record<string, string> = {};
    if (instId) args["inst_id"] = instId;
    const result = await callPythonBridge("get_positions", args) as Position[];
    return result ?? [];
  }

  async getPendingTpsl(instId: string): Promise<TpslOrder[]> {
    const result = await callPythonBridge("get_pending_tpsl", { inst_id: instId }) as TpslOrder[];
    return result ?? [];
  }

  async getFundingRate(instId: string): Promise<FundingRate | null> {
    const result = await callPythonBridge("get_funding_rate", { inst_id: instId }) as FundingRate;
    return result ?? null;
  }

  async getAllFundingRates(): Promise<FundingRate[]> {
    const result = await callPythonBridge("get_all_funding_rates", {}) as FundingRate[];
    return result ?? [];
  }

  async getOrderBook(instId: string): Promise<OrderBook | null> {
    const result = await callPythonBridge("get_order_book", { inst_id: instId }) as OrderBook;
    return result ?? null;
  }

  async setLeverage(instId: string, leverage: number, leverMode = "isolated"): Promise<unknown> {
    return callPythonBridge("set_leverage", {
      inst_id: instId, leverage: String(leverage), lever_mode: leverMode,
    });
  }

  async placeOrder(params: {
    instId: string; side: string; orderType: string; size: string;
    tpTriggerPrice?: string; slTriggerPrice?: string;
  }): Promise<OrderResult> {
    const result = await callPythonBridge("place_order", {
      inst_id: params.instId,
      side: params.side,
      order_type: params.orderType,
      size: params.size,
      tp_trigger_price: params.tpTriggerPrice,
      sl_trigger_price: params.slTriggerPrice,
      margin_mode: "isolated",
    }) as OrderResult;
    return result ?? { orderId: "unknown" };
  }

  async placeTpsl(params: {
    instId: string; side: string; size: string;
    tpTriggerPrice: string; slTriggerPrice: string;
  }): Promise<unknown> {
    return callPythonBridge("place_tpsl", {
      inst_id: params.instId,
      side: params.side,
      size: params.size,
      tp_trigger_price: params.tpTriggerPrice,
      sl_trigger_price: params.slTriggerPrice,
    });
  }

  async cancelOrder(instId: string, orderId: string): Promise<unknown> {
    return callPythonBridge("cancel_order", { inst_id: instId, order_id: orderId });
  }

  async closePosition(instId: string): Promise<unknown> {
    return callPythonBridge("close_position", { inst_id: instId, margin_mode: "isolated" });
  }
}
