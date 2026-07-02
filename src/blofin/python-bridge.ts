/**
 * Blofin Python Bridge
 * Routes API calls through the existing Python BlofinClient which has
 * working Cloudflare WAF bypass via curl_cffi TLS impersonation.
 * Writes args to a temp file to avoid shell quoting issues.
 * 
 * Includes concurrency limiting and retry logic to prevent
 * resource exhaustion from too many simultaneous Python processes.
 */

import { spawn } from "node:child_process";
import { writeFileSync, unlinkSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { logger } from "../utils/logger.js";

const PYTHON_BRIDGE_SCRIPT = "blofin_bridge.py";
const PYTHON_EXE = process.env["PYTHON_PATH"] ?? "C:\\Users\\mknig\\AppData\\Local\\Programs\\Python\\Python312\\python.exe";
const __dirname = dirname(fileURLToPath(import.meta.url));
const BRIDGE_DIR = join(__dirname, "..", "..");

// Concurrency control — max 6 simultaneous Python processes
const MAX_CONCURRENT = 6;
let activeCount = 0;
const queue: Array<() => void> = [];

function acquire(): Promise<void> {
  if (activeCount < MAX_CONCURRENT) {
    activeCount++;
    return Promise.resolve();
  }
  return new Promise<void>((resolve) => {
    queue.push(resolve);
  });
}

function release() {
  if (queue.length > 0) {
    const next = queue.shift()!;
    next();
  } else {
    activeCount--;
  }
}

async function callPythonBridgeOnce(method: string, args: Record<string, unknown> = {}): Promise<unknown> {
  const tmpDir = mkdtempSync(join(tmpdir(), "owl-swarm-"));
  const argsFile = join(tmpDir, "args.json");
  writeFileSync(argsFile, JSON.stringify(args), "utf-8");

  return new Promise((resolve, reject) => {
    const proc = spawn(PYTHON_EXE, [PYTHON_BRIDGE_SCRIPT, method, `@${argsFile}`], {
      cwd: BRIDGE_DIR,
      env: { ...process.env },
      timeout: 45000,
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data: Buffer) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data: Buffer) => {
      stderr += data.toString();
    });

    proc.on("close", (code: number | null) => {
      try { unlinkSync(argsFile); } catch { /* ignore */ }
      try { unlinkSync(tmpDir); } catch { /* ignore */ }

      if (code !== 0) {
        logger.error(`Python bridge error (${method}): code=${code} stderr=${stderr.slice(0, 300)} stdout=${stdout.slice(0, 300)}`);
        try {
          const parsed = JSON.parse(stdout.trim());
          if (parsed.error) {
            reject(new Error(`Blofin API error: ${parsed.error}`));
            return;
          }
          resolve(parsed);
          return;
        }
        catch { /* not JSON */ }
        reject(new Error(`Python bridge exited ${code}: ${stderr.slice(0, 200)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout.trim()));
      }
      catch {
        resolve(stdout.trim());
      }
    });

    proc.on("error", (err: Error) => {
      reject(new Error(`Failed to start Python bridge: ${err.message}. Set PYTHON_PATH env var.`));
    });
  });
}

export async function callPythonBridge(method: string, args: Record<string, unknown> = {}): Promise<unknown> {
  const maxRetries = 2;
  const retryDelayMs = 1000;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    await acquire();
    try {
      const result = await callPythonBridgeOnce(method, args);
      return result;
    } catch (err) {
      if (attempt < maxRetries) {
        logger.warn(`Python bridge retry ${attempt + 1}/${maxRetries} for ${method}: ${err}`);
        await new Promise((r) => setTimeout(r, retryDelayMs * (attempt + 1)));
      } else {
        throw err;
      }
    } finally {
      release();
    }
  }
  throw new Error(`Python bridge failed after ${maxRetries + 1} attempts: ${method}`);
}
