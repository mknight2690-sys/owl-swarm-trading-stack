/** Retry with exponential backoff and circuit breaker */

import { logger } from "./logger.js";

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  retryableStatuses?: number[];
  onRetry?: (attempt: number, error: Error, delayMs: number) => void;
}

const DEFAULT_OPTS: Required<Omit<RetryOptions, "onRetry">> = {
  maxRetries: 6,
  baseDelayMs: 500,
  maxDelayMs: 30000,
  retryableStatuses: [403, 429, 500, 502, 503, 504],
};

export async function withRetry<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {}
): Promise<T> {
  const opts = { ...DEFAULT_OPTS, ...options };
  let lastError: Error | undefined;
  for (let attempt = 0; attempt <= opts.maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt === opts.maxRetries) {
        logger.warn(`All ${opts.maxRetries} retries exhausted: ${lastError.message}`);
        throw lastError;
      }
      const isRetryable = isRetryableError(lastError, opts.retryableStatuses);
      if (!isRetryable) throw lastError;
      const delayMs = Math.min(
        opts.baseDelayMs * Math.pow(2, attempt) + Math.random() * 1000,
        opts.maxDelayMs
      );
      logger.warn(`Retry ${attempt + 1}/${opts.maxRetries} after ${Math.round(delayMs)}ms: ${lastError.message}`);
      if (opts.onRetry) opts.onRetry(attempt + 1, lastError, delayMs);
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }
  throw lastError;
}

function isRetryableError(err: Error, statuses: number[]): boolean {
  const msg = err.message;
  for (const s of statuses) {
    if (msg.includes(String(s))) return true;
  }
  return msg.includes("ECONNRESET") || msg.includes("ETIMEDOUT") || msg.includes("socket hang up");
}

export class CircuitBreaker {
  private counts: Map<string, { count: number; blockedUntil: number }> = new Map();
  constructor(private threshold: number = 8, private resetSec: number = 120) {}
  isBlocked(key: string): boolean {
    const state = this.counts.get(key);
    if (!state) return false;
    if (Date.now() < state.blockedUntil) return true;
    this.counts.delete(key);
    return false;
  }
  recordFailure(key: string): void {
    const state = this.counts.get(key) ?? { count: 0, blockedUntil: 0 };
    state.count++;
    if (state.count >= this.threshold) {
      state.blockedUntil = Date.now() + this.resetSec * 1000;
      logger.warn(`Circuit breaker OPEN for ${key} (${state.count} failures)`);
    }
    this.counts.set(key, state);
  }
  recordSuccess(key: string): void {
    this.counts.delete(key);
  }
}
