import { describe, expect, it } from "vitest";
import { libraryUrl } from "./api";
import { highlight, readUrl, sinceFor, writeUrl } from "./pages/Library";

describe("proof library", () => {
  it("floors the time window to the hour so the CDN can share one answer", () => {
    const now = Date.UTC(2026, 9, 18, 14, 47, 12);
    expect(sinceFor("all", now)).toBeNull();
    expect(sinceFor("24h", now)).toBe("2026-10-17T14:00:00.000Z");
    expect(sinceFor("7d", now)).toBe("2026-10-11T14:00:00.000Z");
  });
  it("round trips the filters through the page URL and drops junk", () => {
    expect(writeUrl(" gdp ", ["FALSE", "TRUE"], "7d")).toBe("/cards?q=gdp&v=FALSE%2CTRUE&t=7d");
    expect(writeUrl("", [], "all")).toBe("/cards");
    expect(readUrl("?q=gdp&v=FALSE,NOPE,TRUE&t=7d")).toEqual({ q: "gdp", verdicts: ["FALSE", "TRUE"], win: "7d" });
    expect(readUrl("?t=forever").win).toBe("all");
  });
  it("builds a stable API url (sorted verdicts = one cache entry)", () => {
    expect(libraryUrl({ q: "", verdicts: [], since: null }, null)).toBe("/api/cards");
    expect(libraryUrl({ q: " gdp ", verdicts: ["TRUE", "FALSE"], since: null }, "abc")).toBe(
      "/api/cards?q=gdp&verdict=FALSE%2CTRUE&cursor=abc",
    );
  });
  it("marks query words in English and Hindi, safely", () => {
    expect(highlight("India GDP grew", "gdp").filter((p) => p.hit).map((p) => p.s)).toEqual(["GDP"]);
    expect(highlight("भारत में 22 भाषाएं", "भाषाएं").some((p) => p.hit && p.s === "भाषाएं")).toBe(true);
    expect(highlight("a (b) c", "(b)").some((p) => p.hit)).toBe(true);
    expect(highlight("text", "")).toEqual([{ s: "text", hit: false }]);
  });
});
