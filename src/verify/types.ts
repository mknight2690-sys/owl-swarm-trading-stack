/** Verification system type definitions */

export interface VerificationResult {
  agentName: string;
  taskId: string;
  status: "pass" | "fail" | "error";
  checkedAt: number;
  details: string;
  discrepancies?: Discrepancy[];
  retryable: boolean;
}

export interface Discrepancy {
  field: string;
  claimed: string;
  actual: string;
  severity: "critical" | "warning" | "info";
}

export interface VerifiedAgentOutput {
  agentName: string;
  taskId: string;
  output: unknown;
  verified: boolean;
  verificationResults: VerificationResult[];
  attempt: number;
  finalStatus: "executed" | "rejected" | "max_retries" | "pending";
}
