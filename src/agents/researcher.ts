/** Research Agent Factory */
export interface ResearchTask {
  instId: string;
  taskId: string;
  context?: string;
}
export interface ResearchOutput {
  instId: string;
  price: number;
  change24h: number;
  volume24h: number;
  trend: "bullish" | "bearish" | "neutral";
  momentumScore: number;
  keyLevels: { support: number; resistance: number; pivot: number };
  fundingRate?: number;
  fundingBias?: string;
  technicalSummary: string;
  suggestedSide: "long" | "short" | "neutral";
  confidence: number;
}
export function createResearcherAgentConfig(agentIndex: number) {
  return {
    agentName: 'Researcher-' + agentIndex,
    model: { id: 'composer-2.5' },
    systemPrompt: 'You are a Market Research AI for Blofin USDT perpetual futures. Analyze the assigned instrument using get_ticker, get_candles, get_funding_rate, get_order_book tools. Output JSON: {instId, price, change24h, volume24h, trend, momentumScore, keyLevels: {support, resistance, pivot}, fundingRate, fundingBias, technicalSummary, suggestedSide, confidence}. Use tools, do not guess. Only suggest long/short if confidence >= 0.5.',
  };
}
