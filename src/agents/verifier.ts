/** Verifier Agent Factory */
export interface VerificationTask {
  agentName: string;
  claimedOutput: Record<string, unknown>;
  fieldsToCheck: string[];
  taskId: string;
}
export interface VerificationOutput {
  status: "pass" | "fail" | "error";
  taskId: string;
  details: string;
  discrepancies: Array<{ field: string; claimed: string; actual: string; severity: "critical" | "warning" | "info" }>;
  retryable: boolean;
}
export const VERIFIER_AGENT_CONFIG = {
  agentName: 'Verifier-Agent',
  model: { id: 'composer-2.5' },
  systemPrompt: 'You are a Verification Agent for Blofin perpetual futures trading. Your ONLY job is to verify that other agents outputs are accurate against live API data. Output a JSON object with: status (pass/fail), details (string), discrepancies (array of {field, claimed, actual, severity}), retryable (boolean).',
};
