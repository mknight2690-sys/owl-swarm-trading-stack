/** Skill library — stores and retrieves verified workflow patterns */

import fs from "node:fs";
import path from "node:path";
import { logger } from "../utils/logger.js";
import type { Skill, Constraint } from "./skill-types.js";

const OUTPUT_DIR = process.env["OUTPUT_DIR"] ?? "outputs";
const SKILLS_DIR = path.join(OUTPUT_DIR, "skills");
const SKILLS_FILE = path.join(SKILLS_DIR, "skills.json");
const CONSTRAINTS_FILE = path.join(OUTPUT_DIR, "CONSTRAINTS.md");

fs.mkdirSync(SKILLS_DIR, { recursive: true });

function loadSkills(): Skill[] {
  try {
    if (!fs.existsSync(SKILLS_FILE)) return [];
    return JSON.parse(fs.readFileSync(SKILLS_FILE, "utf-8"));
  } catch { return []; }
}

function saveSkills(skills: Skill[]): void {
  fs.writeFileSync(SKILLS_FILE, JSON.stringify(skills, null, 2));
}

export function findMatchingSkills(taskPattern: string, tags: string[] = []): Skill[] {
  const skills = loadSkills();
  return skills
    .filter((s) => {
      if (s.successRate < 0.5) return false;
      if (tags.length > 0 && !tags.some((t) => s.tags.includes(t))) return false;
      try {
        const regex = new RegExp(s.taskPattern, "i");
        return regex.test(taskPattern);
      } catch { return false; }
    })
    .sort((a, b) => b.successRate * Math.log(b.useCount + 1) - a.successRate * Math.log(a.useCount + 1));
}

export function saveSkill(skill: Omit<Skill, "id" | "createdAt" | "lastUsedAt" | "useCount" | "successRate">): Skill {
  const skills = loadSkills();
  const id = `skill_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const newSkill: Skill = {
    ...skill, id, createdAt: Date.now(), lastUsedAt: Date.now(),
    useCount: 0, successRate: 1.0,
  };
  skills.push(newSkill);
  saveSkills(skills);
  logger.info(`Saved skill: ${newSkill.name} (${id})`);
  return newSkill;
}

export function recordSkillUse(skillId: string, success: boolean): void {
  const skills = loadSkills();
  const skill = skills.find((s) => s.id === skillId);
  if (!skill) return;
  skill.useCount++;
  skill.lastUsedAt = Date.now();
  // Exponential moving average for success rate
  skill.successRate = skill.successRate * 0.9 + (success ? 0.1 : 0);
  saveSkills(skills);
}

export function getActiveConstraints(): Constraint[] {
  try {
    if (!fs.existsSync(CONSTRAINTS_FILE)) return [];
    const content = fs.readFileSync(CONSTRAINTS_FILE, "utf-8");
    // Parse constraints from markdown
    const constraints: Constraint[] = [];
    const lines = content.split("\n");
    let currentId = "";
    let currentRule = "";
    for (const line of lines) {
      if (line.startsWith("## ")) {
        if (currentId && currentRule) {
          constraints.push({
            id: currentId, rule: currentRule.trim(),
            source: "verification_failure", createdAt: Date.now(),
            violationCount: 0, active: true,
          });
        }
        currentId = line.slice(3).trim();
        currentRule = "";
      } else if (currentId && line.trim() && !line.startsWith("#")) {
        currentRule += line.trim() + " ";
      }
    }
    return constraints;
  } catch { return []; }
}

export function addConstraintFromFailure(rule: string, source: string): void {
  const timestamp = new Date().toISOString();
  const entry = `\n${rule}\n- Source: ${source} | Detected: ${timestamp}\n`;
  if (!fs.existsSync(CONSTRAINTS_FILE)) {
    fs.writeFileSync(CONSTRAINTS_FILE, `# CONSTRAINTS.md — Auto-generated guardrails\n\n___\n${entry}`);
  } else {
    fs.appendFileSync(CONSTRAINTS_FILE, entry);
  }
  logger.info(`Added constraint: ${rule.slice(0, 80)}...`);
}

export function generateConstraintsFromJournal(stats: Record<string, { wins: number; losses: number; totalPnl: number }>): void {
  const avoid: string[] = [];
  for (const [inst, s] of Object.entries(stats)) {
    if (s.losses >= 2 && s.wins === 0) avoid.push(inst);
  }
  if (avoid.length > 0) {
    addConstraintFromFailure(
      `## Avoid repeat losers: ${avoid.join(", ")}`,
      "journal_analysis"
    );
  }
}
