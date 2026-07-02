/** Order parameter verification */

import type { BlofinClient } from "../../blofin/client.js";
import type { Discrepancy } from "../types.js";

export async function verifyInstrumentExists(
  blofin: BlofinClient,
  instId: string
): Promise<Discrepancy | null> {
  try {
    const instruments = await blofin.getInstruments(instId);
    if (instruments.length === 0) {
      return { field: "instId", claimed: instId, actual: "NOT_FOUND", severity: "critical" };
    }
    return null;
  } catch {
    return null;
  }
}

export async function verifyMinSize(
  blofin: BlofinClient,
  instId: string,
  claimedSize: number
): Promise<Discrepancy | null> {
  try {
    const instruments = await blofin.getInstruments(instId);
    if (instruments.length === 0) return null;
    const minSize = Number(instruments[0].minSize);
    if (claimedSize < minSize) {
      return { field: "size", claimed: String(claimedSize), actual: `Minimum is ${minSize}`, severity: "warning" };
    }
    return null;
  } catch {
    return null;
  }
}
