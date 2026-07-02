/** Position verification — checks claimed positions against live Blofin API */

import type { BlofinClient } from "../../blofin/client.js";
import type { Discrepancy } from "../types.js";

export async function verifyPosition(
  blofin: BlofinClient,
  instId: string,
  claimedSize: number
): Promise<Discrepancy | null> {
  try {
    const positions = await blofin.getPositions(instId);
    if (positions.length === 0) {
      if (Math.abs(claimedSize) > 0.001) {
        return { field: "position", claimed: String(claimedSize), actual: "NO_POSITION", severity: "warning" };
      }
      return null;
    }
    const actualSize = Number(positions[0].positions);
    const diff = Math.abs(claimedSize - actualSize);
    if (diff > 0.001) {
      return { field: "position", claimed: String(claimedSize), actual: String(actualSize), severity: "critical" };
    }
    return null;
  } catch {
    return null;
  }
}

export async function verifyNoDuplicatePosition(
  blofin: BlofinClient,
  instId: string
): Promise<Discrepancy | null> {
  try {
    const positions = await blofin.getPositions(instId);
    if (positions.length > 0) {
      const size = Number(positions[0].positions);
      if (Math.abs(size) > 0.001) {
        return { field: "duplicate_position", claimed: "NEW_TRADE", actual: `EXISTS: ${size}`, severity: "critical" };
      }
    }
    return null;
  } catch {
    return null;
  }
}
