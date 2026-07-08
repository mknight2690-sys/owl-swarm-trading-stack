/**
 * Blofin market bridge — Chromium bypasses Cloudflare for live ticker data.
 * Tries WebSocket inside browser; falls back to in-page REST fetch.
 */
import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const OUT =
  process.env.OWL_WS_TICKERS_PATH ||
  path.join(ROOT, "outputs", "ws-tickers.json");
const PRICE_CACHE =
  process.env.BLOFIN_PRICE_CACHE ||
  path.join("C:", "Users", "mknig", "blofin-auto-trader", "outputs", "price-cache.json");
const LOG = path.join(ROOT, "outputs", "ws-bridge.log");

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  try {
    fs.mkdirSync(path.dirname(LOG), { recursive: true });
    fs.appendFileSync(LOG, line + "\n");
  } catch {
    /* ignore */
  }
}

function findChrome() {
  for (const p of CHROME_CANDIDATES) {
    if (p && fs.existsSync(p)) return p;
  }
  return null;
}

function writeCaches(tickers, source) {
  const arr = [...tickers.values()].filter((t) =>
    String(t.instId || "").endsWith("-USDT")
  );
  if (arr.length < 20) return false;

  const now = Date.now() / 1000;
  const payload = {
    updated_at: now,
    source,
    count: arr.length,
    tickers: arr,
  };

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(payload));

  const prices = {};
  for (const t of arr) {
    const inst = t.instId;
    if (!inst) continue;
    prices[inst] = {
      last: t.last || "0",
      open24h: t.open24h || t.last || "0",
      volCurrency24h: t.volCurrency24h || t.vol24h || "0",
    };
  }
  try {
    fs.mkdirSync(path.dirname(PRICE_CACHE), { recursive: true });
    fs.writeFileSync(
      PRICE_CACHE,
      JSON.stringify({ updated_at: now, prices }, null, 0)
    );
  } catch (e) {
    log(`price-cache write failed: ${e.message}`);
  }
  log(`wrote ${arr.length} tickers via ${source}`);
  return true;
}

async function fetchTickersInBrowser(page) {
  return page.evaluate(async () => {
    const res = await fetch(
      "https://api.blofin.com/api/v1/market/tickers?instType=SWAP",
      { credentials: "include" }
    );
    if (!res.ok) return { ok: false, status: res.status, data: [] };
    const body = await res.json();
    return { ok: true, status: res.status, data: body.data || [] };
  });
}

const PYTHON =
  process.env.PYTHON_EXE ||
  "C:\\Users\\mknig\\AppData\\Local\\Programs\\Python\\Python312\\python.exe";

function pythonRefreshLoop() {
  const script = path.join(ROOT, "scripts", "write_universe_cache.py");
  const refreshMs = Number(process.env.OWL_BRIDGE_REFRESH_MS || 60000);
  log("Chromium unavailable — using Python REST refresh loop");
  const run = () => {
    try {
      const out = execSync(`"${PYTHON}" "${script}"`, {
        cwd: ROOT,
        env: { ...process.env, OWL_WS_TICKERS_PATH: OUT },
        timeout: 120000,
      });
      log(String(out).trim());
    } catch (e) {
      log(`python refresh failed: ${e.message}`);
    }
  };
  run();
  setInterval(run, refreshMs);
}

async function main() {
  const chrome = findChrome();
  if (!chrome) {
    log("Chrome not found — using Python REST fallback");
    pythonRefreshLoop();
    return;
  }

  log(`starting Chromium market bridge (${chrome})`);
  const browser = await puppeteer.launch({
    executablePath: chrome,
    headless: false,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--disable-blink-features=AutomationControlled",
      "--window-size=1920,1080",
      "--start-maximized",
    ],
  });

  const page = await browser.newPage();
  await page.evaluateOnNewDocument(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    window.chrome = { runtime: {} };
  });
  await page.setUserAgent(
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
  );

  const tickers = new Map();

  await page.exposeFunction("owlOnTicker", (rows) => {
    const list = Array.isArray(rows) ? rows : [rows];
    for (const r of list) {
      if (r && r.instId) tickers.set(r.instId, r);
    }
  });

  log("loading blofin.com for CF session...");
  await page.goto("https://blofin.com", {
    waitUntil: "networkidle2",
    timeout: 120000,
  });
  await new Promise((r) => setTimeout(r, 30000));

  log("fetching tickers via in-browser REST...");
  let rest = { ok: false, status: 0, data: [] };
  try {
    rest = await fetchTickersInBrowser(page);
  } catch (e) {
    log(`in-browser REST error: ${e.message}`);
  }
  if (rest.ok && rest.data.length) {
    for (const t of rest.data) tickers.set(t.instId, t);
    writeCaches(tickers, "chromium_rest");
  } else {
    log(`in-browser REST failed: status=${rest.status}`);
  }

  log("opening WebSocket inside browser...");
  await page.evaluate(() => {
    if (window.__owlWs) return;
    const ws = new WebSocket("wss://api.blofin.com/ws/public");
    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          op: "subscribe",
          args: [{ channel: "tickers", instType: "SWAP" }],
        })
      );
    };
    ws.onmessage = (ev) => {
      try {
        const p = JSON.parse(ev.data);
        if (p.data) window.owlOnTicker(p.data);
      } catch {
        /* ignore */
      }
    };
    window.__owlWs = ws;
  });

  for (let i = 0; i < 20 && tickers.size < 100; i++) {
    await new Promise((r) => setTimeout(r, 1000));
  }
  log(`tickers after WS wait: ${tickers.size}`);
  if (tickers.size >= 20) {
    writeCaches(tickers, tickers.size > 300 ? "chromium_ws" : "chromium_rest");
  } else {
    log("insufficient chromium tickers — switching to Python REST loop");
    try {
      await browser.close();
    } catch {
      /* ignore */
    }
    pythonRefreshLoop();
    return;
  }

  const refreshMs = Number(process.env.OWL_BRIDGE_REFRESH_MS || 60000);
  setInterval(async () => {
    try {
      rest = await fetchTickersInBrowser(page);
      if (rest.ok && rest.data.length) {
        for (const t of rest.data) tickers.set(t.instId, t);
        writeCaches(tickers, "chromium_rest");
      }
    } catch (e) {
      log(`refresh error: ${e.message}`);
    }
  }, refreshMs);

  process.on("SIGINT", async () => {
    await browser.close();
    process.exit(0);
  });
  process.on("SIGTERM", async () => {
    await browser.close();
    process.exit(0);
  });
}

main().catch((e) => {
  log(`chromium failed: ${e.message} — starting Python fallback`);
  pythonRefreshLoop();
});
