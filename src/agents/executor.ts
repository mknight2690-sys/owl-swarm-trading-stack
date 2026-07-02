/** Execution Agent Factory */
export interface ExecutionTask {
  instId: string;
  side: "buy" | "sell";
  size?: string;
  tpTriggerPrice?: string;
  slTriggerPrice?: string;
  taskId: string;
}
export interface ExecutionOutput {
  instId: string;
  side: string;
  size: string;
  orderId: string;
  status: "filled" | "pending" | "failed";
  entryPrice: number;
  tpTriggerPrice: string;
  slTriggerPrice: string;
  timestamp: number;
}
export function createExecutionAgentConfig(agentIndex: number) {
  return {
    agentName: 'Executor-' + agentIndex,
    model: { id: 'composer-2.5' },
    systemPrompt: 'You are a Trade Execution AI for Blofin perpetual futures. Execute ONE trade with execute_trade(instId, side, size, tpTriggerPrice, slTriggerPrice). Safety: always attach TP/SL, use minimum size, never add to existing positions, set 50x cross leverage. Output JSON: {instId, side, size, orderId, status, entryPrice, tpTriggerPrice, slTriggerPrice, timestamp}. If cannot execute, output {status: failed, reason: explanation}.',
  };
}
