import { describe, expect, it } from "vitest";
import { youtubeId } from "./live";

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
