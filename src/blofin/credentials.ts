/** Load Blofin API credentials from file */

import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import type { BlofinCredentials } from "./types.js";

const DEFAULT_PATH = path.join(
  process.env["BLOFIN_CREDENTIALS_PATH"]
    ? process.env["BLOFIN_CREDENTIALS_PATH"]
    : path.join(os.homedir(), "OneDrive", "Documents", "1B Blofin API.txt")
);

function parseCredentialsText(text: string): BlofinCredentials {
  const fields: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || !trimmed.includes(":")) continue;
    const [key, ...rest] = trimmed.split(":");
    fields[key.trim().toLowerCase().replace(/ /g, "_")] = rest.join(":").trim();
  }
  const apiKey = fields["api_key"] ?? fields["apikey"];
  const secretKey = fields["secret_key"] ?? fields["secretkey"];
  const passphrase = fields["passphrase"];
  if (!apiKey || !secretKey || !passphrase) {
    throw new Error("Credentials file must contain Passphrase, API Key, and Secret Key");
  }
  return { apiKey, secretKey, passphrase };
}

export function loadCredentials(filePath?: string): BlofinCredentials {
  const credPath = filePath ?? DEFAULT_PATH;
  if (!fs.existsSync(credPath)) {
    throw new Error(`Blofin credentials not found: ${credPath}`);
  }
  return parseCredentialsText(fs.readFileSync(credPath, "utf-8"));
}
