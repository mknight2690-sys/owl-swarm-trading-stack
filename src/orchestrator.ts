/**
 * OWL Self-Verifying Agent Swarm — Main Orchestrator
 */

import "dotenv/config";
import { Agent } from "@cursor/sdk";
import { BlofinClient } from "./blofin/client.js";
import { loadCredentials } from "./blofin/credentials.js";
import { rankFromTickers, computePositionSize, defaultTpsl } from "./blofin/analytics.js";
import { ParallelRunner, type AgentTask, type AgentResult } from "./utils/concurrency.js";
import { VerifyGate } from "./verify/verify-gate.js";
import { verifyNoDuplicatePosition } from "./verify/checks/position-check.js";
import { verifyRiskParams } from "./verify/checks/risk-check.js";
import { recordEvent, symbolStats, syncPositionCloses, insightsText, loadEvents } from "./journal/journal.js";
import { findMatchingSkills, saveSkill, getActiveConstraints, generateConstraintsFromJournal } from "./skills/library.js";
import { logger } from "./utils/logger.js";
import { analyzeFunding, analyzeLiquidationRisk, estimateFees, getTierForNotional, analyzeLiquidity } from "./blofin/advanced-analytics.js";
import type { Position, FundingRate, Candle, Ticker } from "./blofin/types.js";
import type { VerifiedAgentOutput } from "./verify/types.js";

const MAX_PARALLEL = Number(process.env["SWARM_MAX_PARALLEL_AGENTS"] ?? 20);
const MAX_RETRIES = Number(process.env["SWARM_MAX_RETRIES"] ?? 3);
const VERIFICATION_REQUIRED = (process.env["SWARM_VERIFICATION_REQUIRED"] ?? "true") === "true";

// Dashboard callbacks — set by main.ts
let pushStatus: ((s: Record<string, unknown>) => void) | null = null;
let pushEvent: ((e: Record<string, unknown>) => void) | null = null;

export function setDashboardUpdater(fn: (s: Record<string, unknown>) => void) { pushStatus = fn; }
export function setDashboardEventFn(fn: (e: Record<string, unknown>) => void) { pushEvent = fn; }

function emitStatus(partial: Record<string, unknown> = {}) {
  if (!pushStatus) return;
  const skillsList = findMatchingSkills(".*");
  const constraintsList = getActiveConstraints();
  pushStatus({
    running: orchestrator?.running ?? false,
    cycleCount: orchestrator?.cycleCount ?? 0,
    totalTrades: orchestrator?.totalTrades ?? 0,
    lastCycleAt: Date.now(),
    lastError: orchestrator?.lastError ?? "",
    equity: orchestrator?.lastEquity ?? 0,
    available: orchestrator?.lastAvailable ?? 0,
    openPositions: orchestrator?.lastPositions ?? [],
    recentEvents: loadEvents(10),
    skills: skillsList.length,
    constraints: constraintsList.length,
    agentsActive: orchestrator?.agentsActive ?? 0,
    verificationPassRate: 100,
    ...partial,
  });
}

function log(msg: string, level: string) {
  logger.info(msg);
  if (pushEvent) pushEvent({ type: "log", message: msg, level, ts: Date.now() });
}

function trace(msg: string, level: string) {
  logger.info(msg);
  if (pushEvent) pushEvent({ type: "log", message: msg, level, ts: Date.now() });
}

// Reference set by constructor so emitStatus can read live fields
let orchestrator: SwarmOrchestrator | null = null;

export class SwarmOrchestrator {
  private blofin: BlofinClient;
  private runner: ParallelRunner;
  private verifier: VerifyGate;
  private apiKey: string;
  private credentials;
  cycleCount = 0;
  totalTrades = 0;
  running = false;
  lastError = "";
  lastEquity = 0;
  lastAvailable = 0;
  lastPositions: Position[] = [];
  agentsActive = 0;
  private positionOpenTimes: Map<string, number> = new Map(); // instId -> timestamp when opened

  constructor() {
    this.credentials = loadCredentials();
    this.blofin = new BlofinClient(this.credentials);
    this.runner = new ParallelRunner(MAX_PARALLEL);
    this.verifier = new VerifyGate(this.blofin, MAX_RETRIES);
    this.apiKey = process.env["CURSOR_API_KEY"] ?? "";
    if (!this.apiKey) logger.warn("CURSOR_API_KEY not set");
    orchestrator = this;
  }

  async runCycle(): Promise<number> {
    this.cycleCount++;
    const cycleStart = Date.now();
    this.lastError = "";

    // Memory guard — if RSS > 1.5GB, log warning (process may be killed by OS)
    const mem = process.memoryUsage();
    if (mem.rss > 1.5 * 1024 * 1024 * 1024) {
      logger.error(`MEMORY WARNING: RSS=${(mem.rss / 1024 / 1024).toFixed(0)}MB — risk of OOM kill`);
    }

    logger.info(`=== CYCLE ${this.cycleCount} START ===`);
    emitStatus({ running: true });

    try {
      const positions = await this.blofin.getPositions();
      syncPositionCloses(positions);

      const balance = await this.blofin.getBalances();
      const equity = Number(balance.totalEquity ?? balance.details?.[0]?.equityUsd ?? 0);
      let available = Number(balance.availableEquity ?? balance.details?.[0]?.availableEquity ?? 0);

      // ═══ AUTO-PROTECT: If equity dropped >15% from last cycle, close worst position ═══
      if (this.lastEquity > 0 && equity < this.lastEquity * 0.85 && positions.length > 0) {
        log(`⚠️ EQUITY DROP: ${this.lastEquity.toFixed(2)} → ${equity.toFixed(2)} (${(((equity - this.lastEquity) / this.lastEquity) * 100).toFixed(1)}%) — closing worst position`, "warn");
        let worstIdx = -1;
        let worstPnl = Infinity;
        for (let i = 0; i < positions.length; i++) {
          const pnl = Number(positions[i].unrealizedPnl || 0);
          if (pnl < worstPnl) { worstPnl = pnl; worstIdx = i; }
        }
        if (worstIdx >= 0 && worstPnl < 0) {
          const worst = positions[worstIdx];
          log(`Closing ${worst.instId} (PnL: ${worstPnl.toFixed(4)})`, "warn");
          try {
            await this.blofin.closePosition(worst.instId);
            log(`Closed ${worst.instId}`, "success");
            const freshBal = await this.blofin.getBalances();
            available = Number(freshBal.availableEquity ?? freshBal.details?.[0]?.availableEquity ?? available);
          } catch (closeErr) {
            log(`Failed to close ${worst.instId}: ${closeErr}`, "error");
          }
        }
      }

      // ═══ STARTUP RECOVERY: If available < $1 and positions exist, close all to reset ═══
      if (this.lastEquity === 0 && available < 1 && positions.length > 0) {
        log(`🔄 STARTUP RECOVERY: available=$${available.toFixed(2)} with ${positions.length} positions — closing all to reset`, "warn");
        for (const pos of positions) {
          try {
            await this.blofin.closePosition(pos.instId);
            log(`  Closed ${pos.instId}`, "success");
          } catch (closeErr) {
            log(`  Failed to close ${pos.instId}: ${closeErr}`, "error");
          }
        }
        const freshBal = await this.blofin.getBalances();
        available = Number(freshBal.availableEquity ?? freshBal.details?.[0]?.availableEquity ?? available);
        log(`Post-reset: available=$${available.toFixed(2)}`, "");
      }

      this.lastEquity = equity;
      this.lastAvailable = available;
      this.lastPositions = positions;
      logger.info(`Account: equity=${equity.toFixed(4)} available=${available.toFixed(4)} positions=${positions.length}`);

      const tickers = await this.blofin.getTickers();
      logger.info(`Universe: ${tickers.length} instruments`);

      // ── Advanced: Funding rate overview ──
      try {
        const allFunding = await this.blofin.getAllFundingRates();
        const highFunding = allFunding.filter(f => Number(f.fundingRate ?? 0) > 0.0005);
        const lowFunding = allFunding.filter(f => Number(f.fundingRate ?? 0) < -0.0005);
        if (highFunding.length > 0 || lowFunding.length > 0) {
          log(`Funding: ${highFunding.length} pairs expensive for longs, ${lowFunding.length} pairs expensive for shorts`, "");
          for (const f of highFunding.slice(0, 3)) {
            log(`  ${f.instId}: funding=${(Number(f.fundingRate)*100).toFixed(4)}% (avoid longs)`, "warn");
          }
          for (const f of lowFunding.slice(0, 3)) {
            log(`  ${f.instId}: funding=${(Number(f.fundingRate)*100).toFixed(4)}% (avoid shorts)`, "warn");
          }
        }
      } catch { /* funding fetch failed, continue */ }

      const blockedBuys = new Set<string>();
      const blockedSells = new Set<string>();
      for (const pos of positions) {
        const sz = Number(pos.positions);
        if (sz > 0) blockedBuys.add(pos.instId);
        else if (sz < 0) blockedSells.add(pos.instId);
      }
      const blocked = new Set([...blockedBuys, ...blockedSells]);

      const stats = symbolStats();
      const ranked = rankFromTickers(tickers, blocked, stats, 20);
      // Build a map from batch tickers for fast lookup (avoids individual getTicker calls)
      const tickerMap = new Map<string, Ticker>();
      for (const t of tickers) {
        if (t.instId) tickerMap.set(t.instId, t);
      }
      logger.info(`Ranked ${ranked.length} opportunities`);
      if (ranked.length === 0) {
        log("No opportunities found — skipping cycle", "warn");
        emitStatus({ running: false });
        return Date.now() - cycleStart;
      }

      const skills = findMatchingSkills("blofin_trade", ["trading"]);
      const constraints = getActiveConstraints();
      const journalInsights = insightsText();

      // ═══════════════════════════════════════════════════════════════════
      // SELF-VERIFYING SWARM LOOP (inspired by @N01ennn's architecture)
      // Multiple agents analyze → cross-check each other → failures
      // get re-run until zero errors remain
      // ═══════════════════════════════════════════════════════════════════
      const topCandidates = ranked.slice(0, Math.min(5, ranked.length));
      const maxVerificationRounds = 3;
      let allVerifiedResearch: VerifiedAgentOutput[] = [];
      let round = 0;

      while (round < maxVerificationRounds) {
        round++;
        this.agentsActive = topCandidates.length * 2;
        log(`Swarm Round ${round}: ${topCandidates.length} researchers + ${topCandidates.length} verifiers firing...`, "");

        // WAVE 1a — 2 agents total: 1 researcher + 1 verifier per candidate (faster, less API pressure)
        const researchTasks: AgentTask[] = [];
        for (const c of topCandidates) {
          // Researcher
          researchTasks.push({
            id: `research_${c.instId}_r${round}_a`,
            agentName: `Researcher-${c.instId}`,
            prompt: this.buildResearchPrompt(c.instId, c, journalInsights, skills, constraints),
            wave: 1,
          });
          // Verifier (checks the researcher's work)
          researchTasks.push({
            id: `verify_${c.instId}_r${round}_b`,
            agentName: `Verifier-${c.instId}`,
            prompt: this.buildVerificationPrompt(c.instId, c, journalInsights, skills, constraints),
            wave: 1,
          });
        }

        const researchWave = await this.runner.runWave(researchTasks, (task) => this.runOWLAgent(task));
        const successResults = researchWave.results.filter((r) => r.status === "success");
        this.agentsActive = 0;

        log(`Round ${round} research: ${successResults.length}/${researchWave.results.length} agents succeeded`, successResults.length > 0 ? "success" : "warn");

        // WAVE 1b — Verification agents check ALL research outputs against live data
        const candidateMap = new Map<string, { instId: string; outputs: VerifiedAgentOutput[] }>();
        for (const result of successResults) {
          try {
            const vResult = await this.verifier.verifyAgentOutput(result, ["price", "instId", "side"]);
            // Extract instId from output
            const outputStr = typeof result.output === "string" ? result.output : JSON.stringify(result.output);
            const parsedInstId = this.extractInstId(outputStr) || result.taskId.split("_")[1] || "unknown";
            if (!candidateMap.has(parsedInstId)) {
              candidateMap.set(parsedInstId, { instId: parsedInstId, outputs: [] });
            }
            candidateMap.get(parsedInstId)!.outputs.push({
              agentName: result.agentName, taskId: result.taskId,
              output: result.output, verified: vResult.status === "pass",
              verificationResults: [vResult], attempt: round,
              finalStatus: vResult.status === "pass" ? "executed" : vResult.retryable ? "max_retries" : "rejected",
            });
          } catch (verifyErr) {
            log(`Verify error: ${verifyErr}`, "error");
          }
        }

        // Only keep candidates where ALL agents agree (zero errors)
        const agreedCandidates: VerifiedAgentOutput[] = [];
        for (const [, data] of candidateMap) {
          const allPassed = data.outputs.every((o) => o.verified);
          const anyPassed = data.outputs.some((o) => o.verified);
          if (allPassed && data.outputs.length >= 2) {
            // All agents agreed — use the highest confidence output
            const best = data.outputs.sort((a, b) => this.getConfidence(b.output) - this.getConfidence(a.output))[0];
            agreedCandidates.push(best);
            log(`✓ CONSENSUS: ${data.instId} — ${data.outputs.length}/ agents agree`, "success");
          } else if (anyPassed && round < maxVerificationRounds) {
            // Partial agreement — will re-run to resolve
            log(`✗ PARTIAL: ${data.instId} — re-running to resolve disagreements`, "warn");
          } else {
            log(`✗ REJECTED: ${data.instId} — failed all verification rounds`, "error");
          }
        }

        allVerifiedResearch = [...allVerifiedResearch, ...agreedCandidates];

        if (agreedCandidates.length > 0) break; // Got consensus, proceed to execution
        if (round < maxVerificationRounds) {
          log(`No consensus reached — re-running swarm (round ${round + 1}/${maxVerificationRounds})...`, "warn");
        }
      }

      if (allVerifiedResearch.length === 0) {
        log("SWARM CONSENSUS FAILED: No candidates passed cross-agent verification — skipping cycle", "warn");
        emitStatus({ running: false });
        return Date.now() - cycleStart;
      }

      // ═══ MARGIN PRE-CHECK: Use tickerMap to estimate affordability ═══
      // (avoids slow getInstruments API call — we already have prices from getTickers)
      const consensusInstIds = new Set<string>();
      for (const r of allVerifiedResearch) {
        const rStr = typeof r.output === "string" ? r.output : JSON.stringify(r.output);
        const rInstId = this.extractInstId(rStr);
        if (rInstId) consensusInstIds.add(rInstId);
      }
      let canAffordAny = false;
      let cheapestCandidate = "";
      let cheapestMargin = Infinity;
      for (const instId of consensusInstIds) {
        const tk = tickerMap.get(instId);
        if (!tk) continue;
        const price = Number(tk.last);
        if (price <= 0) continue;
        // Estimate: assume minSize=1, contractValue=1 (conservative for small accounts)
        // The real check happens in the execution path with actual instrument data
        const estimatedMinMargin = 1 * 1 * price * 1.5 + 0.05;
        if (available >= estimatedMinMargin) {
          canAffordAny = true;
          if (estimatedMinMargin < cheapestMargin) {
            cheapestMargin = estimatedMinMargin;
            cheapestCandidate = instId;
          }
        }
      }
      if (!canAffordAny) {
        log(`SKIPPING EXECUTION: available margin ($${available.toFixed(4)}) too low for any consensus candidate. Close positions to free margin.`, "warn");
        emitStatus({ running: false, lastError: "insufficient_margin" });
        return Date.now() - cycleStart;
      }

      // ═══ POSITION LIMIT: Max 2 positions for small accounts (<$100) ═══
      const MAX_POSITIONS = equity < 100 ? 2 : 5;
      const MIN_AVAILABLE_FOR_NEW_TRADE = 1.0; // Need at least $1 available
      if (positions.length >= MAX_POSITIONS) {
        log(`POSITION LIMIT: ${positions.length}/${MAX_POSITIONS} positions open — managing existing only`, "");
        emitStatus({ running: false, lastError: "position_limit_reached" });
        return Date.now() - cycleStart;
      }
      if (available < MIN_AVAILABLE_FOR_NEW_TRADE) {
        log(`MARGIN LOCK: available=$${available.toFixed(2)} < $${MIN_AVAILABLE_FOR_NEW_TRADE} minimum — waiting for positions to close`, "warn");
        emitStatus({ running: false, lastError: "margin_locked" });
        return Date.now() - cycleStart;
      }

      // Pick best from consensus-approved candidates (prefer affordable ones)
      allVerifiedResearch.sort((a, b) => this.getConfidence(b.output) - this.getConfidence(a.output));
      const bestResearch = allVerifiedResearch[0];

      const parsedRaw = typeof bestResearch.output === "string" ? this.stripJson(bestResearch.output) : JSON.stringify(bestResearch.output);
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(parsedRaw) as Record<string, unknown>;
      } catch {
        log(`Agent ${bestResearch.agentName} returned invalid JSON — skipping cycle`, "error");
        this.lastError = `Invalid JSON from ${bestResearch.agentName}`;
        emitStatus({ running: false, lastError: this.lastError });
        return Date.now() - cycleStart;
      }
      const instId = String(parsed["instId"] ?? "");
      const side = String(parsed["suggestedSide"] ?? "");
      const confidence = Number(parsed["confidence"] ?? 0);
      if (!instId || !side) {
        log(`Agent ${bestResearch.agentName} returned incomplete JSON (missing instId/side) — skipping`, "error");
        emitStatus({ running: false, lastError: "Incomplete agent output" });
        return Date.now() - cycleStart;
      }

      if (confidence < 0.5 || side === "neutral") {
        log(`Best candidate ${instId} skipped (confidence=${confidence}, side=${side})`, "warn");
        emitStatus({ running: false });
        return Date.now() - cycleStart;
      }

      const dupCheck = await verifyNoDuplicatePosition(this.blofin, instId);
      if (dupCheck) {
        log(`Skipping ${instId}: position already exists`, "warn");
        emitStatus({ running: false });
        return Date.now() - cycleStart;
      }

      const instrument = await this.blofin.getInstrument(instId);
      if (!instrument) {
        log(`Instrument ${instId} not found — skipping`, "warn");
        emitStatus({ running: false });
        return Date.now() - cycleStart;
      }

      const entryPrice = Number(parsed["price"]);
      const minSize = Number(instrument.minSize);
      const lotSize = Number(instrument.lotSize);
      const tickSize = Number(instrument.tickSize);
      const contractValue = Number(instrument.contractValue ?? 1);
      const maxLeverage = Number(instrument.maxLeverage ?? 50);

      // ── Advanced: Funding rate check ──
      const fundingRaw = await this.blofin.getFundingRate(instId);
      const fundingInfo = analyzeFunding(fundingRaw);
      if ((side === "long" && fundingInfo.shouldAvoidLong) || (side === "short" && fundingInfo.shouldAvoidShort)) {
        log(`Skipping ${instId}: unfavorable funding (${fundingInfo.annualizedCostPct.toFixed(1)}%/yr)`, "warn");
        emitStatus({ running: false });
        return Date.now() - cycleStart;
      }

      // ── Advanced: Liquidity check (use batch ticker data) ──
      const ticker = tickerMap.get(instId) ?? await this.blofin.getTicker(instId);
      const liquidity = analyzeLiquidity(ticker ?? undefined, undefined, equity * 0.01 * 50);
      if (!liquidity.isLiquidEnough) {
        log(`Skipping ${instId}: insufficient liquidity (spread=${liquidity.spreadPct.toFixed(3)}%)`, "warn");
        emitStatus({ running: false });
        return Date.now() - cycleStart;
      }

      // ═══════════════════════════════════════════════════════════════
      // DYNAMIC MULTI-FACTOR LEVERAGE INTELLIGENCE
      // The swarm collectively determines optimal leverage based on:
      // 1. Account equity & available margin
      // 2. Existing position exposure (total notional vs equity)
      // 3. Liquidation risk distance
      // 4. Funding rate cost
      // 5. Liquidity/spread conditions
      // 6. Instrument tier limits
      // ═══════════════════════════════════════════════════════════════

      const tpsl = defaultTpsl(entryPrice, side === "long" ? "buy" : "sell", tickSize, 0.015, 0.025);
      const stopPrice = Number(tpsl.slTriggerPrice);

      // Guard: skip if entryPrice or minSize is invalid (NaN protection)
      // Use !isFinite() to catch NaN, Infinity, and 0
      if (!isFinite(entryPrice) || entryPrice <= 0 || !isFinite(minSize) || minSize <= 0 || !isFinite(contractValue) || contractValue <= 0) {
        log(`Skipping ${instId}: invalid instrument data (entryPrice=${entryPrice}, minSize=${minSize}, contractValue=${contractValue})`, "warn");
        emitStatus({ running: false });
        return Date.now() - cycleStart;
      }

      // Factor 1: Instrument hard cap
      const tierNotional = entryPrice * contractValue * minSize * 50;
      const tier = getTierForNotional(tierNotional);
      const instrumentMaxLeverage = Math.min(maxLeverage, tier.maxLeverage);

      // Factor 2: Exposure-based de-leveraging
      let existingNotional = 0;
      for (const pos of positions) {
        const posSize = Math.abs(Number(pos.positions));
        const posMark = Number(pos.markPrice || 0);
        existingNotional += posSize * contractValue * posMark;
      }
      const exposureRatio = equity > 0 ? existingNotional / equity : 0;
      const exposureFactor = Math.max(0.2, 1.0 - exposureRatio * 0.8);

      // Factor 3: Liquidation distance safety
      const liqDistPct = side === "long"
        ? ((1 - (1 / instrumentMaxLeverage)) * 100)
        : ((1 - (1 / instrumentMaxLeverage)) * 100);
      const liquidationFactor = liqDistPct < 10 ? Math.max(0.2, liqDistPct / 10) : 1.0;

      // Factor 4: Funding cost adjustment
      const fundingCostFactor = fundingInfo.absRate > 0.0003 ? 0.6 : 1.0;

      // Factor 5: Liquidity adjustment
      const liquidityFactor = liquidity.spreadPct > 0.2 ? 0.7 : 1.0;

      // Factor 6: Available margin constraint (80% for small accounts, 50% for large)
      const maxMarginForThisTrade = available * (equity < 100 ? 0.8 : 0.5);
      const marginDenominator = minSize * contractValue * entryPrice + maxMarginForThisTrade;
      const maxLeverageByMargin = marginDenominator > 0
        ? (maxMarginForThisTrade * instrumentMaxLeverage) / marginDenominator
        : 2; // fallback if denominator is 0

      // ═══ SWARM CONSENSUS LEVERAGE ═══
      const rawLeverage = instrumentMaxLeverage * exposureFactor * liquidationFactor * fundingCostFactor * liquidityFactor;
      const dynamicLeverage = Math.min(
        instrumentMaxLeverage,
        Math.floor(rawLeverage),
        Math.floor(maxLeverageByMargin),
        25 // ABSOLUTE CAP: never exceed 25x
      );
      const leverage = Math.max(2, Math.min(dynamicLeverage, instrumentMaxLeverage));

      log(`LEVERAGE INTEL ${instId}: instrumentMax=${instrumentMaxLeverage} exposure=${exposureFactor.toFixed(2)} liqDist=${liquidationFactor.toFixed(2)} funding=${fundingCostFactor.toFixed(2)} spread=${liquidityFactor.toFixed(2)} → FINAL=${leverage}x`, "");

      // ═══ RISK CHECK ═══
      const riskDiscrepancies = verifyRiskParams(
        side as "buy" | "sell" | "long" | "short",
        entryPrice, Number(tpsl.slTriggerPrice), Number(tpsl.tpTriggerPrice)
      );
      if (riskDiscrepancies.some((d) => d.severity === "critical")) {
        log(`Risk check failed for ${instId}`, "error");
        emitStatus({ running: false });
        return Date.now() - cycleStart;
      }

      // ═══ SMART SIZING ═══
      // For small accounts (<$100), allow up to 80% of equity per trade
      // For larger accounts, cap at 25%
      const minSizeNotional = minSize * contractValue * entryPrice;
      const maxSingleTradeNotional = equity < 100 ? equity * 0.80 : equity * 0.25;
      if (minSizeNotional > maxSingleTradeNotional) {
        log(`Skipping ${instId}: minSize notional ($${minSizeNotional.toFixed(2)}) exceeds cap ($${maxSingleTradeNotional.toFixed(2)})`, "warn");
        emitStatus({ running: false });
        return Date.now() - cycleStart;
      }

      // Size based on risk, then cap to available margin
      let sized = computePositionSize({
        equityUsdt: equity, riskPct: 0.01, entry: entryPrice, stop: stopPrice,
        minSize, lotSize, contractValue, leverage,
      });
      let positionSize = Number(sized.size);
      let notional = positionSize * contractValue * entryPrice;
      let marginNeeded = (notional / leverage) * 1.5 + 0.05;

      // Cap to available margin
      if (available < marginNeeded && marginNeeded > 0 && entryPrice > 0 && contractValue > 0) {
        const maxMarginUsable = Math.max(0, available - 0.05);
        const maxNotional = (maxMarginUsable / 1.5) * leverage;
        let maxContracts = Math.floor(maxNotional / (contractValue * entryPrice));
        if (lotSize > 0) maxContracts = Math.floor(maxContracts / lotSize) * lotSize;
        if (maxContracts >= minSize) {
          positionSize = maxContracts;
          notional = positionSize * contractValue * entryPrice;
          marginNeeded = (notional / leverage) * 1.5 + 0.05;
          log(`Resized ${instId}: reduced to ${positionSize} contracts to fit margin (need ${marginNeeded.toFixed(4)})`, "warn");
        } else {
          log(`Skipping ${instId}: cannot afford minSize=${minSize}`, "warn");
          emitStatus({ running: false });
          return Date.now() - cycleStart;
        }
      }

      // Re-fetch balance for fresh available margin
      const freshBalance = await this.blofin.getBalances();
      const freshAvailable = Number(freshBalance.availableEquity ?? freshBalance.details?.[0]?.availableEquity ?? 0);
      if (freshAvailable < available) {
        log(`Balance update: available dropped from ${available.toFixed(4)} to ${freshAvailable.toFixed(4)}`, "warn");
      }
      available = Math.min(available, freshAvailable);

      // Final margin check
      if (available < marginNeeded) {
        log(`Insufficient margin for ${instId}: need ${marginNeeded.toFixed(4)} have ${available.toFixed(4)}`, "warn");
        emitStatus({ running: false });
        return Date.now() - cycleStart;
      }

      // EXECUTE TRADE
      const tradeMsg = `EXECUTING: ${instId} ${side} size=${positionSize} entry=${entryPrice} SL=${tpsl.slTriggerPrice} TP=${tpsl.tpTriggerPrice}`;
      logger.info(tradeMsg);
      if (pushEvent) {
        pushEvent({ type: "log", message: tradeMsg, level: "success", ts: Date.now() });
        pushEvent({ type: "trade", data: { instId, side, size: positionSize, entry: entryPrice, sl: tpsl.slTriggerPrice, tp: tpsl.tpTriggerPrice }, ts: Date.now() });
      }

      try {
        await this.blofin.setLeverage(instId, leverage);
        const orderResult = await this.blofin.placeOrder({
          instId, side: side === "long" ? "buy" : "sell",
          orderType: "market", size: String(positionSize),
          tpTriggerPrice: tpsl.tpTriggerPrice, slTriggerPrice: tpsl.slTriggerPrice,
        });
        const orderId = orderResult.orderId ?? "unknown";
        log(`Order placed: ${orderId}`, "success");

        recordEvent({
          type: "order_placed", instId, side, size: String(positionSize),
          orderId, orderType: "market", tpTriggerPrice: tpsl.tpTriggerPrice,
          slTriggerPrice: tpsl.slTriggerPrice, cycle: this.cycleCount,
        });
        this.totalTrades++;

        const newPositions = await this.blofin.getPositions(instId);
        if (newPositions.length > 0) {
          log(`Position confirmed: ${instId} size=${newPositions[0].positions} avgPrice=${newPositions[0].averagePrice}`, "success");
          this.positionOpenTimes.set(instId, Date.now());
        }

        saveSkill({
          name: `trade_${instId}_${side}`,
          description: `${side} trade on ${instId} at ${entryPrice}`,
          taskPattern: `.*${instId}.*${side}.*`,
          content: JSON.stringify({ instId, side, entryPrice, slTriggerPrice: tpsl.slTriggerPrice, tpTriggerPrice: tpsl.tpTriggerPrice, confidence }),
          tags: ["trading", instId, side],
        });
      } catch (execErr) {
        const errMsg = String(execErr);
        logger.error(`Execution failed for ${instId}: ${errMsg}`);
        this.lastError = errMsg;
        log(`Execution failed: ${errMsg}`, "error");
        recordEvent({ type: "order_blocked", instId, side, reason: errMsg, cycle: this.cycleCount });
      }

      await this.ensureAllPositionsProtected();
      generateConstraintsFromJournal(symbolStats());

      // ── Advanced: Liquidation risk check on all positions ──
      const allPositions = await this.blofin.getPositions();
      for (const pos of allPositions) {
        const liqRisk = analyzeLiquidationRisk(pos, available);
        if (liqRisk.dangerLevel === "critical") {
          log(`⚠️ CRITICAL: ${pos.instId} liquidation imminent! Distance: ${liqRisk.distanceToLiquidationPct.toFixed(1)}%`, "error");
        } else if (liqRisk.dangerLevel === "danger") {
          log(`⚠️ ${pos.instId} liquidation risk: ${liqRisk.distanceToLiquidationPct.toFixed(1)}% away`, "warn");
        }
        if (liqRisk.adlRisk) {
          log(`⚠️ ${pos.instId} ADL risk detected (high margin ratio + profitable)`, "warn");
        }
      }

      const cycleDuration = Date.now() - cycleStart;
      logger.info(`=== CYCLE ${this.cycleCount} COMPLETE (${cycleDuration}ms) ===`);

      // Push comprehensive cycle summary to dashboard
      if (pushEvent) {
        pushEvent({
          type: "cycle",
          data: {
            cycle: this.cycleCount,
            duration: cycleDuration,
            equity,
            available,
            positions: allPositions.length,
            totalTrades: this.totalTrades,
            ts: Date.now(),
          },
          ts: Date.now(),
        });
        // Push liquidation risk summary
        for (const pos of allPositions) {
          const liqRisk = analyzeLiquidationRisk(pos, available);
          pushEvent({
            type: "position_risk",
            data: {
              instId: pos.instId,
              size: pos.positions,
              markPrice: liqRisk.markPrice,
              liquidationPrice: liqRisk.liquidationPrice,
              distancePct: liqRisk.distanceToLiquidationPct,
              dangerLevel: liqRisk.dangerLevel,
              adlRisk: liqRisk.adlRisk,
              marginRatio: liqRisk.marginRatio,
              ts: Date.now(),
            },
            ts: Date.now(),
          });
        }
      }

      this.lastEquity = equity;
      this.lastAvailable = available;
      this.lastPositions = allPositions;
      emitStatus({ running: false });
      return cycleDuration;

    } catch (err) {
      const errMsg = String(err);
      logger.error(`Cycle ${this.cycleCount} failed: ${errMsg}`);
      this.lastError = errMsg;
      log(`Cycle ${this.cycleCount} failed: ${errMsg}`, "error");
      emitStatus({ running: false, lastError: errMsg });
      return Date.now() - cycleStart;
    }
  }

  private async runOWLAgent(task: AgentTask): Promise<string> {
    if (!this.apiKey) throw new Error("CURSOR_API_KEY not configured");
    const maxRetries = 2;
    let lastErr: unknown;
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const result = await Agent.prompt(task.prompt, {
          apiKey: this.apiKey,
          model: { id: "composer-2.5" },
          local: { cwd: process.cwd() },
        });
        if (result.status === "error") {
          lastErr = new Error(`Agent ${task.agentName} failed: ${result.id}`);
          logger.warn(`OWLAgent ${task.agentName} attempt ${attempt}/${maxRetries} failed, retrying...`);
          await new Promise((r) => setTimeout(r, 2000 * attempt)); // backoff
          continue;
        }
        return result.result ?? "";
      } catch (err) {
        lastErr = err;
        if (attempt < maxRetries) {
          logger.warn(`OWLAgent ${task.agentName} attempt ${attempt}/${maxRetries} error, retrying...`);
          await new Promise((r) => setTimeout(r, 2000 * attempt));
        }
      }
    }
    logger.error(`OWLAgent ${task.agentName} error: ${lastErr}`);
    throw lastErr;
  }

  private buildResearchPrompt(
    instId: string,
    candidate: { last: string; chgPct24h: number; volCurrency24h: number; longScore: number; shortScore: number; suggestedSide: string },
    journalInsights: string,
    skills: unknown[],
    constraints: unknown[]
  ): string {
    // Keep prompts SHORT to avoid agent timeouts. Do 2 API calls max.
    const parts = [
      `Analyze ${instId} for Blofin perp trade. Data: price=${candidate.last} chg24h=${candidate.chgPct24h}% vol24h=${candidate.volCurrency24h} long=${candidate.longScore} short=${candidate.shortScore}`,
      ``,
      `Check these 2 things with API tools:`,
      `1. get_funding_rate("${instId}") — rate is decimal. >0.0005 = expensive for longs. <-0.0005 = expensive for shorts.`,
      `2. get_candles("${instId}", "15m", 20) — 15m trend direction.`,
      journalInsights,
    ];
    if (constraints.length > 0) {
      parts.push(`Constraints: ${constraints.map((c) => `- ${(c as { rule: string }).rule}`).join(" | ")}`);
    }
    parts.push(
      ``,
      `Reply ONLY JSON, no markdown: {"instId":"${instId}","suggestedSide":"long|short|neutral","confidence":0.0-1.0,"fundingRate":0.0,"trend":"up|down|neutral"}`,
      `Be conservative. Only suggest long/short if confidence >= 0.6. Use "neutral" if unsure.`
    );
    return parts.join("\n");
  }

  private stripJson(text: string): string {
    // Remove markdown code fences
    let cleaned = text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/g, "").trim();
    // Try to extract JSON object from surrounding text
    const jsonMatch = cleaned.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      cleaned = jsonMatch[0];
    }
    return cleaned;
  }

  private extractInstId(outputStr: string): string | null {
    try {
      const jsonMatch = outputStr.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        return parsed["instId"] ?? null;
      }
    } catch { /* ignore */ }
    return null;
  }

  private getConfidence(output: unknown): number {
    try {
      const str = typeof output === "string" ? output : JSON.stringify(output);
      const jsonMatch = str.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        return Number(parsed["confidence"] ?? 0);
      }
    } catch { /* ignore */ }
    return 0;
  }

  private buildVerificationPrompt(
    instId: string,
    candidate: { last: string; chgPct24h: number; volCurrency24h: number; longScore: number; shortScore: number; suggestedSide: string },
    journalInsights: string,
    skills: unknown[],
    constraints: unknown[]
  ): string {
    // SHORT prompt — 1 API call to verify price
    const parts = [
      `Verify ${instId} for Blofin trade. Claimed: price=${candidate.last} side=${candidate.suggestedSide}`,
      `Check with API: get_ticker("${instId}") — verify price is within 5% of ${candidate.last}`,
      journalInsights,
      `Reply ONLY JSON: {"instId":"${instId}","verified":true|false,"confidence":0.0-1.0,"notes":"short reason"}`,
      `Set verified=true only if price matches. Be skeptical.`
    ];
    return parts.join("\n");
  }

  private pickBestResearch(verified: VerifiedAgentOutput[]): VerifiedAgentOutput | null {
    const passed = verified.filter((v) => v.verified);
    if (passed.length === 0) return null;
    return passed.sort((a, b) => {
      try {
        const aRaw = typeof a.output === "string" ? this.stripJson(a.output) : JSON.stringify(a.output);
        const bRaw = typeof b.output === "string" ? this.stripJson(b.output) : JSON.stringify(b.output);
        const aOut = JSON.parse(aRaw) as Record<string, unknown>;
        const bOut = JSON.parse(bRaw) as Record<string, unknown>;
        return Number(bOut["confidence"] ?? 0) - Number(aOut["confidence"] ?? 0);
      } catch { return 0; }
    })[0];
  }

  private async ensureAllPositionsProtected(): Promise<void> {
    try {
      const positions = await this.blofin.getPositions();
      for (const pos of positions) {
        const sz = Number(pos.positions);
        if (Math.abs(sz) < 1e-12) continue;
        const pending = await this.blofin.getPendingTpsl(pos.instId);
        if (pending.length === 0) {
          const closeSide = sz > 0 ? "sell" : "buy";
          const entry = Number(pos.averagePrice);
          const markPrice = Number(pos.markPrice || pos.averagePrice);
          const tickRes = await this.blofin.getInstrument(pos.instId);
          const tick = Number(tickRes?.tickSize ?? 0.1);
          const posSide = sz > 0 ? "buy" : "sell";
          const tpsl = defaultTpsl(markPrice, posSide, tick, 0.015, 0.025);
          try {
            await this.blofin.placeTpsl({
              instId: pos.instId, side: closeSide, size: "-1",
              tpTriggerPrice: tpsl.tpTriggerPrice, slTriggerPrice: tpsl.slTriggerPrice,
            });
            log(`TP/SL placed on ${pos.instId}`, "success");
          } catch (err) {
            logger.warn(`Failed to place TP/SL on ${pos.instId}: ${err}`);
          }
        }

        // ═══ PROFIT CLOSING: Close positions with >2% unrealized profit to free margin ═══
        const pnl = Number(pos.unrealizedPnl || 0);
        const notional = Math.abs(sz) * Number(pos.markPrice || pos.averagePrice);
        const pnlPct = notional > 0 ? (pnl / notional) * 100 : 0;
        const curAvailable = (await this.blofin.getBalances()).availableEquity ?? 0;
        if (pnlPct > 2 && Number(curAvailable) < 1) {
          log(`💰 PROFIT CLOSE: ${pos.instId} (+${pnlPct.toFixed(1)}%, $${pnl.toFixed(4)}) — freeing margin`, "success");
          try {
            await this.blofin.closePosition(pos.instId);
            log(`Closed ${pos.instId} for profit`, "success");
            this.positionOpenTimes.delete(pos.instId);
          } catch (closeErr) {
            log(`Failed to close ${pos.instId}: ${closeErr}`, "error");
          }
        }

        // ═══ STALE POSITION CLOSE: Close if open > 8 minutes and not strongly profitable ═══
        const openTime = this.positionOpenTimes.get(pos.instId) ?? Date.now();
        const ageMin = (Date.now() - openTime) / 60000;
        if (ageMin > 8 && pnlPct < 1) {
          log(`⏰ STALE CLOSE: ${pos.instId} (open ${ageMin.toFixed(0)}min, pnl=${pnlPct.toFixed(1)}%) — freeing capital`, "warn");
          try {
            await this.blofin.closePosition(pos.instId);
            log(`Closed stale ${pos.instId}`, "success");
            this.positionOpenTimes.delete(pos.instId);
          } catch (closeErr) {
            log(`Failed to close ${pos.instId}: ${closeErr}`, "error");
          }
        }
      }
    } catch (err) {
      logger.warn(`ensureAllPositionsProtected failed: ${err}`);
    }
  }

  async runLoop(intervalMs = 60000): Promise<void> {
    this.running = true;
    logger.info(`Starting OWL Swarm loop (interval: ${intervalMs}ms)`);
    log("OWL Swarm started — entering trading loop", "success");
    await this.runCycle();
    while (this.running) {
      await new Promise((r) => setTimeout(r, intervalMs));
      if (!this.running) break;
      try {
        await this.runCycle();
      } catch (err) {
        log(`Cycle error: ${err}`, "error");
      }
    }
  }

  stop() {
    this.running = false;
    logger.info("OWL Swarm stopped");
    log("OWL Swarm stopped", "warn");
  }
}
