/** Blofin API type definitions */

export interface BlofinCredentials {
  apiKey: string;
  secretKey: string;
  passphrase: string;
}

export interface Ticker {
  instId: string;
  last: string;
  open24h: string;
  high24h: string;
  low24h: string;
  volCurrency24h: string;
  vol24h: string;
  ts: string;
  chgPct?: number;
  bidPrice?: string;
  askPrice?: string;
}

export interface Instrument {
  instId: string;
  instType: string;
  minSize: string;
  lotSize: string;
  tickSize: string;
  maxLeverage: string;
  contractValue: string;
}

export interface Position {
  instId: string;
  positions: string;
  side: string;
  averagePrice: string;
  markPrice: string;
  unrealizedPnl: string;
  realizedPnl: string;
  leverage: string;
  marginMode: string;
  marginRatio?: string;
}

export interface Balance {
  totalEquity: string;
  availableEquity: string;
  details?: Array<{
    equityUsd: string;
    availableEquity: string;
  }>;
}

export interface OrderResult {
  orderId: string;
  code: string;
  msg: string;
}

export interface TpslOrder {
  id: string;
  instId: string;
  side: string;
  tpTriggerPrice: string;
  slTriggerPrice: string;
  state: string;
}

export interface Candle {
  ts: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface FundingRate {
  instId: string;
  fundingRate: string;
  fundingTime: string;
}

export interface OrderBook {
  bids: [string, string][];
  asks: [string, string][];
  ts: string;
}

export interface ApiError {
  code: string;
  msg: string;
}

export interface BlofinApiResponse<T = unknown> {
  code: string;
  msg: string;
  data: T;
}
