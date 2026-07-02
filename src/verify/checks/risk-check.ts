/** Risk parameter verification — checks SL/TP placement */

import type { Discrepancy } from "../types.js";

export function verifyRiskParams(
  side: "buy" | "sell" | "long" | "short",
  entryPrice: number,
  slTriggerPrice: number,
  tpTriggerPrice: number
): Discrepancy[] {
  const discrepancies: Discrepancy[] = [];
  const isLong = side === "buy" || side === "long";

  if (isLong) {
    if (slTriggerPrice >= entryPrice) {
      discrepancies.push({
        field: "slTriggerPrice",
        claimed: String(slTriggerPrice),
        actual: `Must be below entry (${entryPrice}) for long`,
        severity: "critical",
      });
    }
    if (tpTriggerPrice <= entryPrice) {
      discrepancies.push({
        field: "tpTriggerPrice",
        claimed: String(tpTriggerPrice),
        actual: `Must be above entry (${entryPrice}) for long`,
        severity: "critical",
      });
    }
  } else {
    if (slTriggerPrice <= entryPrice) {
      discrepancies.push({
        field: "slTriggerPrice",
        claimed: String(slTriggerPrice),
        actual: `Must be above entry (${entryPrice}) for short`,
        severity: "critical",
      });
    }
    if (tpTriggerPrice >= entryPrice) {
      discrepancies.push({
        field: "tpTriggerPrice",
        claimed: String(tpTriggerPrice),
        actual: `Must be below entry (${entryPrice}) for short`,
        severity: "critical",
      });
    }
  }

  // Check reward:risk ratio
  const riskDist = Math.abs(entryPrice - slTriggerPrice);
  const rewardDist = Math.abs(tpTriggerPrice - entryPrice);
  if (riskDist > 0 && rewardDist / riskDist < 1.5) {
    discrepancies.push({
      field: "rewardRiskRatio",
      claimed: String(Math.round((rewardDist / riskDist) * 100) / 100),
      actual: "Minimum 1.5:1 required",
      severity: "warning",
    });
  }

  return discrepancies;
}

export function verifySide(side: string): Discrepancy | null {
  const validSides = ["buy", "sell", "long", "short"];
  if (!validSides.includes(side.toLowerCase())) {
    return { field: "side", claimed: side, actual: "Must be buy/sell/long/short", severity: "critical" };
  }
  return null;
}
