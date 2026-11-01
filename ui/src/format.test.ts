import { describe, expect, it } from "vitest";

import { caseClass, catalogueNo, pct, score, usd } from "./format";

describe("format", () => {
  it("numbers specimens like a catalogue", () => {
    expect(catalogueNo(7)).toBe("MM·0007");
    expect(catalogueNo(12345)).toBe("MM·12345");
  });

  it("formats measurements and money", () => {
    expect(pct(0.845)).toBe("85%");
    expect(pct(null)).toBe("n/a");
    expect(score(0.756)).toBe("0.76");
    expect(usd(0)).toBe("$0");
    expect(usd(0.0042)).toBe("$0.0042");
    expect(usd(1.5)).toBe("$1.50");
  });

  it("marks passes rescued by the baseline as excused", () => {
    expect(caseClass({ status: "pass", excused_by_baseline: true })).toBe("st-excused");
    expect(caseClass({ status: "violation", excused_by_baseline: false })).toBe("st-violation");
  });
});
