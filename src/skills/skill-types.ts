/** Skill library type definitions */

export interface Skill {
  id: string;
  name: string;
  description: string;
  taskPattern: string;       // Regex pattern to match against incoming tasks
  createdAt: number;
  lastUsedAt: number;
  useCount: number;
  successRate: number;       // 0-1
  content: string;           // The actual skill content (prompt fragment, workflow, etc.)
  tags: string[];
}

export interface Constraint {
  id: string;
  rule: string;              // Human-readable constraint
  source: "verification_failure" | "manual" | "journal_analysis";
  createdAt: number;
  violationCount: number;
  active: boolean;
}
