import { afterEach, describe, expect, it, vi } from "vitest";

// A slow token refresh: the id token arrives after the socket would already be open.
vi.mock("./auth", () => ({
  idToken: () => new Promise<string>((ok) => setTimeout(() => ok("tok"), 20)),
}));

import { openLive, youtubeId, youtubeWatchLink } from "./live";

class OpensFast {
  static made: OpensFast[] = [];
  binaryType = "";
  sent: unknown[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  constructor(readonly url: string) {
    OpensFast.made.push(this);
    setTimeout(() => this.onopen?.(), 1); // opens long before the token is back
  }
  send(d: unknown) {
    this.sent.push(d);
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  OpensFast.made = [];
});

describe("openLive", () => {
  it("never misses the open event while the token refreshes", async () => {
    vi.stubGlobal("WebSocket", OpensFast);
    vi.stubGlobal("location", { origin: "https://proof.example" });
    const ws = await Promise.race([
      openLive("sess-1234", () => {}),
      new Promise<null>((ok) => setTimeout(() => ok(null), 500)),
    ]);
    expect(ws).not.toBeNull();
    expect(OpensFast.made).toHaveLength(1);
    expect(OpensFast.made[0]?.sent[0]).toBe(JSON.stringify({ type: "auth", token: "tok" }));
  });
});

describe("youtube links", () => {
  it("youtu.be ids are validated like every other form", () => {
    expect(youtubeId("https://youtu.be/dQw4w9WgXcQ?si=x")).toBe("dQw4w9WgXcQ");
    expect(youtubeId("https://youtu.be/not-a-real-link")).toBeNull();
    expect(youtubeId("https://youtu.be/")).toBeNull();
  });

  it("any YouTube form becomes the one https link the server accepts", () => {
    const want = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";
    for (const u of [
      " https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10 ",
      "http://youtube.com/watch?v=dQw4w9WgXcQ",
      "https://m.youtube.com/live/dQw4w9WgXcQ?feature=share",
      "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
      "https://youtu.be/dQw4w9WgXcQ?si=x",
    ]) {
      expect(youtubeWatchLink(u)).toBe(want);
    }
    expect(youtubeWatchLink("https://vimeo.com/123")).toBeNull();
    expect(youtubeWatchLink("not a link")).toBeNull();
  });
});
