/** Parallel agent runner with wave-based execution */

import { logger } from "./logger.js";

export interface AgentTask {
  id: string;
  agentName: string;
  prompt: string;
  wave: number;
  dependsOn?: string[];
  maxRetries?: number;
}

export interface AgentResult {
  taskId: string;
  agentName: string;
  status: "success" | "error" | "timeout";
  output: string;
  durationMs: number;
  error?: string;
}

export interface WaveResult {
  wave: number;
  results: AgentResult[];
  completedAt: number;
  allSucceeded: boolean;
}

export class ParallelRunner {
  private maxParallel: number;
  private results: Map<string, AgentResult> = new Map();

  constructor(maxParallel = 20) {
    this.maxParallel = maxParallel;
  }

  async runWave(
    tasks: AgentTask[],
    executor: (task: AgentTask) => Promise<string>,
    timeoutMs = 300000
  ): Promise<WaveResult> {
    const wave = tasks[0]?.wave ?? 0;
    logger.info(`Starting wave ${wave}: ${tasks.length} parallel agents`);
    const results: AgentResult[] = [];
    for (let i = 0; i < tasks.length; i += this.maxParallel) {
      const batch = tasks.slice(i, i + this.maxParallel);
      const batchResults = await Promise.all(
        batch.map((task) => this.runSingle(task, executor, timeoutMs))
      );
      results.push(...batchResults);
    }
    const allSucceeded = results.every((r) => r.status === "success");
    logger.info(`Wave ${wave} complete: ${results.filter((r) => r.status === "success").length}/${results.length} succeeded`);
    return { wave, results, completedAt: Date.now(), allSucceeded };
  }

  async runAllWaves(
    waves: Map<number, AgentTask[]>,
    executor: (task: AgentTask) => Promise<string>,
    timeoutMs = 300000,
    stopOnWaveFailure = true
  ): Promise<WaveResult[]> {
    const sortedWaves = Array.from(waves.entries()).sort((a, b) => a[0] - b[0]);
    const allResults: WaveResult[] = [];
    for (const [waveNum, tasks] of sortedWaves) {
      const waveResult = await this.runWave(tasks, executor, timeoutMs);
      allResults.push(waveResult);
      if (stopOnWaveFailure && !waveResult.allSucceeded) {
        logger.warn(`Wave ${waveNum} had failures - stopping pipeline`);
        break;
      }
    }
    return allResults;
  }

  private async runSingle(
    task: AgentTask,
    executor: (task: AgentTask) => Promise<string>,
    timeoutMs: number
  ): Promise<AgentResult> {
    const start = Date.now();
    try {
      const output = await this.withTimeout(executor(task), timeoutMs, task);
      const result: AgentResult = {
        taskId: task.id, agentName: task.agentName,
        status: "success", output, durationMs: Date.now() - start,
      };
      this.results.set(task.id, result);
      return result;
    } catch (err) {
      const result: AgentResult = {
        taskId: task.id, agentName: task.agentName,
        status: "error", output: "", durationMs: Date.now() - start,
        error: err instanceof Error ? err.message : String(err),
      };
      this.results.set(task.id, result);
      return result;
    }
  }

  private withTimeout(promise: Promise<string>, ms: number, task: AgentTask): Promise<string> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`Agent ${task.agentName} timed out after ${ms}ms`)), ms);
      promise.then((val) => { clearTimeout(timer); resolve(val); }).catch((err) => { clearTimeout(timer); reject(err); });
    });
  }

  getResult(taskId: string): AgentResult | undefined {
    return this.results.get(taskId);
  }

  getResultsByAgent(agentName: string): AgentResult[] {
    return Array.from(this.results.values()).filter((r) => r.agentName === agentName);
  }
}
