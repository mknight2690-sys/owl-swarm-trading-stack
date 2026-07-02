/** Test SSE live stream — verify equity updates every 500ms */
import http from "node:http";

let lastEquity = 0;
let count = 0;
const startTime = Date.now();

const req = http.get("http://127.0.0.1:7878/events", (res) => {
  let buf = "";
  res.on("data", (chunk) => {
    buf += chunk.toString();
    const lines = buf.split("\n\n");
    buf = lines.pop(); // keep incomplete
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const msg = JSON.parse(line.slice(6));
        if (msg.type === "live") {
          const eq = msg.data.equity;
          const pnl = eq - lastEquity;
          const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
          const pnlStr = pnl !== 0 ? ` (${pnl >= 0 ? '+' : ''}${pnl.toFixed(4)})` : '';
          process.stdout.write(`\r[${elapsed}s] Equity: $${eq.toFixed(2)}${pnlStr}   `);
          lastEquity = eq;
          count++;
        }
      } catch { /* skip */ }
    }
  });
});

req.on("error", (e) => console.error("Error:", e.message));

// Stop after 30s
setTimeout(() => {
  req.destroy();
  console.log(`\n\nReceived ${count} live updates in 30s`);
  console.log(`Average interval: ${(30000 / count).toFixed(0)}ms`);
  process.exit(0);
}, 30000);
