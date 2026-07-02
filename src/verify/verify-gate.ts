/** Verification Gate — the core self-verifying loop engine */

import type { BlofinClient } from "../blofin/client.js";
import type { Position, Balance, Ticker } from "../blofin/types.js";
import type { VerificationResult, Discrepancy, VerifiedAgentOutput } from "./types.js";
import type { AgentResult } from "../utils/concurrency.js";
import { logger } from "../utils/logger.js";
import { addConstraintFromFailure } from "../skills/library.js";

export class VerifyGate {
  private blofin: BlofinClient;
  private maxRetries: number;
  private tickerCache: Ticker[] | null = null;
  private tickerCacheTs = 0;
  private balanceCache: Balance | null = null;
  private balanceCacheTs = 0;

  constructor(blofin: BlofinClient, maxRetries = 3) {
    this.blofin = blofin;
    this.maxRetries = maxRetries;
  }

  private async getTickersCached(): Promise<Ticker[]> {
    const now = Date.now();
    if (!this.tickerCache || now - this.tickerCacheTs > 30000) {
      this.tickerCache = await this.blofin.getTickers();
      this.tickerCacheTs = now;
    }
    return this.tickerCache;
  }

  private async getBalanceCached(): Promise<Balance> {
    const now = Date.now();
    if (!this.balanceCache || now - this.balanceCacheTs > 15000) {
      this.balanceCache = await this.blofin.getBalances();
      this.balanceCacheTs = now;
    }
    return this.balanceCache;
  }

  async verifyAgentOutput(result: AgentResult, expectedFields: string[]): Promise<VerificationResult> {
    const discrepancies: Discrepancy[] = [];
    let status: "pass" | "fail" | "error" = "pass";
    let details = `Verified output from ${result.agentName}`;

    try {
      const raw = typeof result.output === "string" ? result.output.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/g, "").trim() : JSON.stringify(result.output);
      const output = JSON.parse(raw) as Record<string, unknown>;
      // Check each expected field
      for (const field of expectedFields) {
        const check = await this.verifyField(field, output[field], output);
        if (check) discrepancies.push(check);
      }
      if (discrepancies.length > 0) {
        status = "fail";
        details = `Found ${discrepancies.length} discrepancies in ${result.agentName} output`;
        logger.warn(`Verification failed for ${result.agentName}: ${details}`);
        for (const d of discrepancies) {
          logger.warn(`  ${d.field}: claimed="${d.claimed}" actual="${d.actual}" (${d.severity})`);
        }
      }
    } catch {
      // Non-JSON output — check as text
      logger.info(`Non-JSON output from ${result.agentName}, skipping field verification`);
    }

    return {
      agentName: result.agentName,
      taskId: result.taskId,
      status,
      checkedAt: Date.now(),
      details,
      discrepancies: discrepancies.length > 0 ? discrepancies : undefined,
      retryable: status === "fail" && !discrepancies.some((d) => d.severity === "critical"),
    };
  }

  private async verifyField(field: string, claimed: unknown, fullOutput: Record<string, unknown>): Promise<Discrepancy | null> {
    if (claimed === undefined || claimed === null) return null;
    const claimedStr = String(claimed);
    try {
      switch (field) {
        case "price":
        case "last":
        case "markPrice": {
          const instId = this.extractInstId(fullOutput);
          if (!instId) return null;
          const allTickers = await this.getTickersCached();
          const ticker = allTickers.find((t) => t.instId === instId);
          if (!ticker) return null;
          const actual = ticker.last;
          const diff = Math.abs(Number(claimedStr) - Number(actual));
          const diffPct = diff / Number(actual) * 100;
          if (diffPct > 5) {
            return { field, claimed: claimedStr, actual, severity: "critical" };
          } else if (diffPct > 1) {
            return { field, claimed: claimedStr, actual, severity: "warning" };
          }
          return null;
        }
        case "equity":
        case "totalEquity": {
          const balance = await this.getBalanceCached();
          const actual = String(balance.totalEquity ?? balance.details?.[0]?.equityUsd ?? "0");
          const diff = Math.abs(Number(claimedStr) - Number(actual));
          if (diff > 1) return { field, claimed: claimedStr, actual, severity: "warning" };
          return null;
        }
        case "positionSize":
        case "size": {
          const instId = this.extractInstId(fullOutput);
          if (!instId) return null;
          const positions = await this.blofin.getPositions(instId);
          if (positions.length === 0) return null;
          const actual = positions[0].positions;
          const diff = Math.abs(Number(claimedStr) - Number(actual));
          if (diff > 0.001) return { field, claimed: claimedStr, actual, severity: "critical" };
          return null;
        }
        case "instId": {
          // Verify instrument exists
          try {
            const inst = await this.blofin.getInstrument(claimedStr);
            if (!inst) return { field, claimed: claimedStr, actual: "NOT_FOUND", severity: "critical" };
          } catch { /* skip if WAF blocked */ }
          return null;
        }
        case "side": {
          const validSides = ["buy", "sell", "long", "short"];
          if (!validSides.includes(claimedStr.toLowerCase())) {
            return { field, claimed: claimedStr, actual: "must be buy/sell/long/short", severity: "critical" };
          }
          return null;
        }
        case "slTriggerPrice":
        case "tpTriggerPrice": {
          // Verify SL is below entry for longs, above entry for shorts
          const entry = Number(fullOutput["entryPrice"] ?? fullOutput["entry"] ?? 0);
          const side = String(fullOutput["side"] ?? fullOutput["suggestedSide"] ?? "").toLowerCase();
          const price = Number(claimedStr);
          if (entry > 0 && !isNaN(price)) {
            if ((side === "buy" || side === "long") && price >= entry) {
              return { field, claimed: claimedStr, actual: "SL must be below entry for long", severity: "critical" };
            }
            if ((side === "sell" || side === "short") && price <= entry) {
              return { field, claimed: claimedStr, actual: "SL must be above entry for short", severity: "critical" };
            }
          }
          return null;
        }
        default:
          return null;
      }
    } catch (err) {
      logger.warn(`Verification check failed for field ${field}: ${err}`);
      return null;
    }
  }

  private extractInstId(output: Record<string, unknown>): string | null {
    return String(output["instId"] ?? output["instrument"] ?? output["symbol"] ?? "") || null;
  }

  async verifyAndRetry(
    results: AgentResult[],
    expectedFieldsMap: Record<string, string[]>,
    executor: (taskId: string, feedback: string) => Promise<AgentResult>,
  ): Promise<VerifiedAgentOutput[]> {
    const verified: VerifiedAgentOutput[] = [];
    for (const result of results) {
      const expectedFields = expectedFieldsMap[result.agentName] ?? [];
      let attempt = 1;
      let currentResult = result;
      let feedback = "";
      const verificationResults: VerificationResult[] = [];

      while (attempt <= this.maxRetries) {
        const vResult = await this.verifyAgentOutput(currentResult, expectedFields);
        verificationResults.push(vResult);

        if (vResult.status === "pass") {
          verified.push({
            agentName: result.agentName, taskId: result.taskId,
            output: currentResult.output, verified: true,
            verificationResults, attempt,
            finalStatus: "executed",
          });
          break;
        }

        if (!vResult.retryable || attempt >= this.maxRetries) {
          verified.push({
            agentName: result.agentName, taskId: result.taskId,
            output: currentResult.output, verified: false,
            verificationResults, attempt,
            finalStatus: vResult.retryable ? "max_retries" : "rejected",
          });
          // Add constraint from failure
          const constraint = `Agent ${result.agentName}: ${vResult.details}${vResult.discrepancies?.map((d) => ` [${d.field}: claimed=${d.claimed} actual=${d.actual}]`).join("; ")}`;
          addConstraintFromFailure(constraint, "verification_failure");
          break;
        }

        // Retry with feedback
        feedback = `VERIFICATION FAILED (attempt ${attempt}): ${vResult.details}. ${vResult.discrepancies?.map((d) => `Field "${d.field}": you claimed "${d.claimed}" but live API shows "${d.actual}".`).join(" ")} Please re-check your work and correct.`;
        currentResult = await executor(result.taskId, feedback);
        attempt++;
      }
    }
    return verified;
  }
}
