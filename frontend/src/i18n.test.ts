import { describe, expect, it } from "vitest";
import { DICTS, format, initialLang, type Key } from "./i18n";
import { VERDICT } from "./verdict";

const vars = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("i18n", () => {
  it("has every key in Hindi, non empty, with the same placeholders", () => {
    const keys = Object.keys(DICTS.en) as Key[];
    expect(Object.keys(DICTS.hi).sort()).toEqual([...keys].sort());
    for (const k of keys) {
      expect(DICTS.hi[k].trim(), k).not.toBe("");
      expect(vars(DICTS.hi[k]), k).toEqual(vars(DICTS.en[k]));
    }
  });

  it("verdict words match the card image (verdict.ts)", () => {
    for (const v of ["TRUE", "MISLEADING", "FALSE", "UNVERIFIABLE"] as const) {
      expect(DICTS.hi[`verdict.${v}`]).toBe(VERDICT[v].hi);
      expect(DICTS.en[`verdict.${v}`]).toBe(VERDICT[v].en);
    }
  });

  it("picks saved choice, then browser language", () => {
    expect(initialLang("hi", ["en-US"])).toBe("hi");
    expect(initialLang(null, ["hi-IN", "en"])).toBe("hi");
    expect(initialLang(null, ["en-IN"])).toBe("en");
    expect(initialLang("xx", [])).toBe("en");
  });

  it("formats placeholders and leaves unknown ones", () => {
    expect(format("{done} of {total}", { done: 3, total: 12 })).toBe("3 of 12");
    expect(format("{x}", {})).toBe("{x}");
  });
});
