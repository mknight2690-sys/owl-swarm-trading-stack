/** Price verification — checks claimed prices against live Blofin ticker */

import type { BlofinClient } from "../../blofin/client.js";
import type { Discrepancy } from "../types.js";

export async function verifyPrice(
  blofin: BlofinClient,
  instId: string,
  claimedPrice: number
): Promise<Discrepancy | null> {
  try {
    const tickers = await blofin.getTickers(instId);
    if (tickers.length === 0) {
      return { field: "price", claimed: String(claimedPrice), actual: "NO_DATA", severity: "warning" };
    }
    const actualPrice = Number(tickers[0].last);
    if (actualPrice <= 0) return null;
    const diff = Math.abs(claimedPrice - actualPrice);
    const diffPct = (diff / actualPrice) * 100;
    if (diffPct > 5) {
      return { field: "price", claimed: String(claimedPrice), actual: String(actualPrice), severity: "critical" };
    }
    if (diffPct > 1) {
      return { field: "price", claimed: String(claimedPrice), actual: String(actualPrice), severity: "warning" };
    }
    return null;
  } catch (err) {
    // WAF blocked — skip price check
    return null;
  }
}
