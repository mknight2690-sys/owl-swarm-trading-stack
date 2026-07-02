import http from "node:http";

function get(path) {
  return new Promise((resolve, reject) => {
    http.get(`http://127.0.0.1:7878${path}`, (res) => {
      let data = "";
      res.on("data", (d) => data += d);
      res.on("end", () => resolve(JSON.parse(data)));
    }).on("error", reject);
  });
}

async function main() {
  console.log("=== Dashboard Status ===");
  const status = await get("/api/status");
  console.log(JSON.stringify(status, null, 2));

  console.log("\n=== Recent Events ===");
  const events = await get("/api/events");
  console.log(`Event count: ${events.length}`);
  for (const e of events.slice(-5)) {
    console.log(`  [${e.level||''}] ${e.message||e.type||JSON.stringify(e).slice(0,80)}`);
  }
}

main().catch(console.error);
