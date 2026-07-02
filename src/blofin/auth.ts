/** HMAC-SHA256 request signing for Blofin API */

import { createHmac } from "node:crypto";
import { randomUUID } from "node:crypto";
import type { BlofinCredentials } from "./types.js";

export function signRequest(
  credentials: BlofinCredentials,
  method: string,
  pathWithQuery: string,
  bodyStr: string
): { timestamp: string; nonce: string; signature: string } {
  const timestamp = String(Date.now());
  const nonce = randomUUID();
  const prehash = `${pathWithQuery}${method.toUpperCase()}${timestamp}${nonce}${bodyStr}`;
  const hexSig = createHmac("sha256", credentials.secretKey)
    .update(prehash)
    .digest("hex");
  const signature = Buffer.from(hexSig).toString("base64");
  return { timestamp, nonce, signature };
}

export function buildAuthHeaders(
  credentials: BlofinCredentials,
  method: string,
  pathWithQuery: string,
  bodyStr: string
): Record<string, string> {
  const { timestamp, nonce, signature } = signRequest(
    credentials,
    method,
    pathWithQuery,
    bodyStr
  );
  return {
    "ACCESS-KEY": credentials.apiKey,
    "ACCESS-SIGN": signature,
    "ACCESS-TIMESTAMP": timestamp,
    "ACCESS-NONCE": nonce,
    "ACCESS-PASSPHRASE": credentials.passphrase,
  };
}
