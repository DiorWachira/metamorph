import { describe, expect, it } from "vitest";

import { baseLife, creature, lifeAt, stageOf } from "./life";

describe("the life cycle", () => {
  it("runs through the four stages in order", () => {
    expect([0, 0.3, 0.7, 0.9].map(stageOf)).toEqual(["ovum", "larva", "pupa", "imago"]);
  });

  it("carries a page from its own stage to the butterfly as you scroll", () => {
    expect(lifeAt(baseLife("/runs"), 0)).toBeCloseTo(0.22);
    expect(lifeAt(baseLife("/runs"), 1)).toBe(1);
    expect(lifeAt(0.5, 7)).toBe(1); // overscroll stays in range
  });

  it("gives each page a stage: unscrollable pages still show their creature", () => {
    expect(stageOf(baseLife("/"))).toBe("ovum");
    expect(stageOf(baseLife("/runs/abc"))).toBe("larva");
    expect(stageOf(baseLife("/relations"))).toBe("pupa");
    expect(stageOf(baseLife("/lab"))).toBe("imago");
  });

  it("never shows the caterpillar and the butterfly together", () => {
    for (let life = 0; life <= 1; life += 0.005) {
      const now = creature(life);
      expect(now.butterfly && now.larvaOpacity > 0).toBe(false);
    }
  });
});
