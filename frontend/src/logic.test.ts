import { describe, expect, it } from "vitest";
import { errorText } from "./api";
import { domain, progress, VERDICT } from "./verdict";

describe("progress", () => {
  it("counts proved and failed as done", () => {
    expect(progress({ proved: 3, failed: 1, queued: 2, checking: 1 })).toEqual({ done: 4, total: 7 });
    expect(progress({})).toEqual({ done: 0, total: 0 });
  });
});

describe("errorText", () => {
  it("maps FastAPI validation errors to one readable line", () => {
    const detail = [{ loc: ["body", "youtube_url"], msg: "Value error, youtube_url must be an https YouTube link" }];
    expect(errorText(422, detail)).toBe("youtube_url: youtube_url must be an https YouTube link");
  });
  it("handles auth, rate limit and unknown shapes", () => {
    expect(errorText(401, undefined)).toMatch(/sign in/);
    expect(errorText(429, "slow down")).toMatch(/wait/);
    expect(errorText(404, "not found")).toBe("not found");
    expect(errorText(500, { x: 1 })).toMatch(/500/);
  });
});

describe("verdict meta", () => {
  it("always pairs colour with a word and icon", () => {
    for (const v of Object.values(VERDICT)) {
      expect(v.en).toBeTruthy();
      expect(v.icon).toBeTruthy();
      expect(v.hi).toBeTruthy();
    }
  });
  it("extracts a clean domain", () => {
    expect(domain("https://www.rbi.org.in/x?y=1")).toBe("rbi.org.in");
    expect(domain("not a url")).toBe("not a url");
  });
});
