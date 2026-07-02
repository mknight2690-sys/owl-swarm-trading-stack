/** OWL Swarm 60-Minute Monitor
 * Runs the swarm and logs status every 60 seconds for 60 intervals.
 */

import "dotenv/config";
import { startDashboardServer, updateStatus } from "./dashboard/server.js";
import { SwarmOrchestrator, setDashboardUpdater } from "./orchestrator.js";
import { logger } from "./utils/logger.js";
import { symbolStats, loadEvents } from "./journal/journal.js";

const TOTAL_INTERVALS = 60;
const INTERVAL_MS = 60_000;

async function main() {
  logger.info("========================================");
  logger.info("  OWL SWARM — 60-MINUTE LIVE MONITOR   ");
  logger.info("========================================");

  // Start dashboard
  const server = startDashboardServer();
  setDashboardUpdater(updateStatus);

  // Create orchestrator
  const orchestrator = new SwarmOrchestrator();

  // Handle shutdown
  let shuttingDown = false;
  const shutdown = () => {
    if (shuttingDown) return;
    shuttingDown = true;
    logger.info("Shutdown signal received");
    orchestrator.stop();
    server.close();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  // Run cycles with monitoring
  for (let i = 1; i <= TOTAL_INTERVALS; i++) {
    if (shuttingDown) break;

    logger.info(`\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
    logger.info(`  INTERVAL ${i}/${TOTAL_INTERVALS} — ${new Date().toISOString()}`);
    logger.info(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);

    const cycleStart = Date.now();

    try {
      const duration = await orchestrator.runCycle();
      const elapsed = Date.now() - cycleStart;

      // Log summary
      const stats = symbolStats();
      const events = loadEvents(5);
      logger.info(`Cycle complete: ${duration}ms wall: ${elapsed}ms`);
      logger.info(`Stats: ${JSON.stringify(stats)}`);
      logger.info(`Recent events: ${events.length}`);

      // Update dashboard
      updateStatus({
        running: true,
        cycleCount: i,
        totalTrades: orchestrator["totalTrades"],
        equity: 0,
        available: 0,
      });

    } catch (err) {
      logger.error(`Cycle ${i} failed: ${err}`);
    }

    // Wait for next interval (unless last)
    if (i < TOTAL_INTERVALS && !shuttingDown) {
      logger.info(`Waiting ${INTERVAL_MS / 1000}s until next interval...`);
      await new Promise((r) => setTimeout(r, INTERVAL_MS));
    }
  }

  logger.info("\n========================================");
  logger.info("  60-MINUTE MONITOR COMPLETE            ");
  logger.info("========================================");

  // Keep dashboard alive for a bit
  await new Promise((r) => setTimeout(r, 30000));
  server.close();
}

main().catch((err) => {
  logger.error(`Monitor fatal: ${err}`);
  process.exit(1);
});
