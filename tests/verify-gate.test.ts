import { describe, it, expect } from "vitest";
import { verifyRiskParams, verifySide } from "../src/verify/checks/risk-check.js";

describe("verifyRiskParams", () => {
  it("should pass for correct long SL/TP", () => {
    const result = verifyRiskParams("long", 100, 98, 103);
    expect(result.filter((d) => d.severity === "critical")).toHaveLength(0);
  });
  it("should fail for long with SL above entry", () => {
    const result = verifyRiskParams("long", 100, 101, 103);
    expect(result.some((d) => d.field === "slTriggerPrice" && d.severity === "critical")).toBe(true);
  });
  it("should fail for short with SL below entry", () => {
    const result = verifyRiskParams("short", 100, 99, 97);
    expect(result.some((d) => d.field === "slTriggerPrice" && d.severity === "critical")).toBe(true);
  });
  it("should warn on low reward:risk ratio", () => {
    const result = verifyRiskParams("long", 100, 99, 100.5);
    expect(result.some((d) => d.field === "rewardRiskRatio" && d.severity === "warning")).toBe(true);
  });
});

describe("verifySide", () => {
  it("should pass for valid sides", () => {
    expect(verifySide("buy")).toBeNull();
    expect(verifySide("sell")).toBeNull();
    expect(verifySide("long")).toBeNull();
    expect(verifySide("short")).toBeNull();
  });
  it("should fail for invalid side", () => {
    const result = verifySide("hold");
    expect(result).not.toBeNull();
    expect(result!.severity).toBe("critical");
  });
});
