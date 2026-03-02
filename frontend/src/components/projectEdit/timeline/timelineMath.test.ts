import { describe, expect, it } from "vitest";

import { buildRulerTicks, clamp, findClosest, mergeRanges } from "./timelineMath";

describe("timelineMath", () => {
  it("clamp clamps into range", () => {
    expect(clamp(5, 0, 10)).toBe(5);
    expect(clamp(-1, 0, 10)).toBe(0);
    expect(clamp(11, 0, 10)).toBe(10);
  });

  it("findClosest returns null when no candidate within delta", () => {
    expect(findClosest([0, 10, 20], 15, 4)).toBeNull();
  });

  it("findClosest picks closest within delta", () => {
    expect(findClosest([0, 10, 20], 14, 6)).toBe(10);
    expect(findClosest([0, 10, 20], 18, 6)).toBe(20);
  });

  it("mergeRanges merges overlaps and sorts", () => {
    const merged = mergeRanges([
      { id: "b", startMs: 1000, endMs: 2000 },
      { id: "a", startMs: 0, endMs: 500 },
      { id: "c", startMs: 400, endMs: 900 },
    ]);
    expect(merged).toHaveLength(2);
    expect(merged[0].startMs).toBe(0);
    expect(merged[0].endMs).toBe(900);
    expect(merged[1].startMs).toBe(1000);
    expect(merged[1].endMs).toBe(2000);
  });

  it("buildRulerTicks yields majors and minors", () => {
    const { ticks, majorStepMs } = buildRulerTicks(0, 10_000, 10);
    expect(majorStepMs).toBeGreaterThan(0);
    expect(ticks.some((t) => t.kind === "major")).toBe(true);
    expect(ticks.some((t) => t.kind === "minor")).toBe(true);
  });
});

