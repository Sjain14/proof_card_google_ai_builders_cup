import { describe, expect, it } from "vitest";
import { clock, replayDue, youtubeId } from "./live";

describe("youtubeId", () => {
  it("reads every YouTube link shape", () => {
    expect(youtubeId("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10")).toBe("dQw4w9WgXcQ");
    expect(youtubeId("https://youtu.be/dQw4w9WgXcQ?si=x")).toBe("dQw4w9WgXcQ");
    expect(youtubeId("https://m.youtube.com/shorts/dQw4w9WgXcQ")).toBe("dQw4w9WgXcQ");
    expect(youtubeId("https://www.youtube.com/live/dQw4w9WgXcQ")).toBe("dQw4w9WgXcQ");
  });
  it("refuses anything else", () => {
    expect(youtubeId("https://evil.example/watch?v=dQw4w9WgXcQ")).toBeNull();
    expect(youtubeId("https://www.youtube.com/watch?v=short")).toBeNull();
    expect(youtubeId("not a url")).toBeNull();
  });
});

describe("replay", () => {
  it("shows only live cards the video has reached, newest first", () => {
    const claims = [
      { id: "a", source: "live", t_offset_s: 5 },
      { id: "b", source: "live", t_offset_s: 86 },
      { id: "c", source: "predicted", t_offset_s: 1 },
      { id: "d", source: "live", t_offset_s: null },
      { id: "e", source: "live", t_offset_s: 14 },
    ];
    expect(replayDue(claims, 20).map((c) => c.id)).toEqual(["e", "a"]);
    expect(replayDue(claims, 0)).toEqual([]);
  });
  it("formats m:ss", () => {
    expect(clock(86.7)).toBe("1:26");
    expect(clock(4)).toBe("0:04");
  });
});
