import { Agent } from "@cursor/sdk";
import "dotenv/config";

console.log("Testing Agent.prompt()...");

try {
  const result = await Agent.prompt("Say hello in 5 words.", {
    apiKey: process.env.CURSOR_API_KEY,
    model: { id: "composer-2.5" },
    local: { cwd: process.cwd() },
  });
  console.log("Status:", result.status);
  console.log("Result:", result.result?.slice(0, 200));
} catch (err) {
  console.error("Error:", err.message);
  if (err.stack) console.error("Stack:", err.stack.slice(0, 500));
}
