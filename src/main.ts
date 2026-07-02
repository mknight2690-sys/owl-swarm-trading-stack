/** OWL Swarm — Combined entry point: Dashboard + Trading Loop */

import "dotenv/config";
import { startDashboardServer, updateStatus, addDashboardEvent } from "./dashboard/server.js";
import { SwarmOrchestrator, setDashboardUpdater, setDashboardEventFn } from "./orchestrator.js";
import { logger } from "./utils/logger.js";

async function main() {
  // Start dashboard server
  const server = startDashboardServer();

  // Connect orchestrator to dashboard (status updates + event log)
  setDashboardUpdater(updateStatus);
  setDashboardEventFn(addDashboardEvent);

  // Start the trading loop
  const orchestrator = new SwarmOrchestrator();
  const intervalMs = Number(process.env["CYCLE_INTERVAL_MS"] ?? 60000);

  // Handle graceful shutdown
  process.on("SIGINT", () => {
    logger.info("Shutting down OWL Swarm...");
    orchestrator.stop();
    server.close();
    process.exit(0);
  });

  process.on("SIGTERM", () => {
    orchestrator.stop();
    server.close();
    process.exit(0);
  });

  await orchestrator.runLoop(intervalMs);
}

// Catch unhandled rejections to prevent silent crashes
process.on("unhandledRejection", (reason) => {
  logger.error(`Unhandled rejection: ${reason}`);
});

process.on("uncaughtException", (err) => {
  logger.error(`Uncaught exception: ${err}`);
  process.exit(1);
});

// Log exit cause
process.on("exit", (code) => {
  logger.error(`Process exiting with code ${code}`);
});

main().catch((err) => {
  logger.error(`Fatal: ${err}`);
  process.exit(1);
});
