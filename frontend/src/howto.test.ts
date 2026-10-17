import { describe, expect, it } from "vitest";
import { tgText } from "./components/CardTile";
import { isSampleVideo, SAMPLE, SAMPLE_VIDEO_ID, wantsSample } from "./sample";
import { youtubeId } from "./live";

describe("sample", () => {
  it("fills every field and points at the same clip the live page sends", () => {
    for (const v of Object.values(SAMPLE)) expect(v.trim().length).toBeGreaterThan(0);
    expect(youtubeId(SAMPLE.youtube)).toBe(SAMPLE_VIDEO_ID);
    expect(isSampleVideo(youtubeId(SAMPLE.youtube))).toBe(true);
    expect(isSampleVideo("dQw4w9WgXcQ")).toBe(false);
  });
  it("opens prefilled from the how-to page link only", () => {
    expect(wantsSample("?sample=1")).toBe(true);
    expect(wantsSample("?sample=trump")).toBe(true); // old shared links keep working
    expect(wantsSample("")).toBe(false);
    expect(wantsSample("?sample=other")).toBe(false);
  });
});

describe("telegram share text", () => {
  it("arrives written: verdict + claim, long claims cut", () => {
    expect(tgText("FALSE", "We ended eight wars")).toBe("FALSE: “We ended eight wars” · Proof Card");
    expect(tgText(null, "x")).toBe("“x” · Proof Card");
    expect(tgText("TRUE", "a".repeat(300)).length).toBeLessThan(170);
  });
});
