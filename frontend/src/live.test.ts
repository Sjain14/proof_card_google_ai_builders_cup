import { afterEach, describe, expect, it, vi } from "vitest";
import { mergeFeed, type FeedClaim } from "./api";
import { backoffMs, clock, pollRetry, connectLive, MAX_RETRIES, replayDue, youtubeId, type LiveEvent } from "./live";

class FakeSocket {
  readyState = 1;
  sent: unknown[] = [];
  onclose: ((c: { code: number }) => void) | null = null;
  send(d: unknown) { this.sent.push(d); }
  close() { this.readyState = 3; }
  drop(code: number) { this.readyState = 3; this.onclose?.({ code }); }
}

function harness(fails: boolean[] = []) {
  const socks: FakeSocket[] = [];
  const states: string[] = [];
  const reopened = vi.fn();
  let emit: (e: LiveEvent) => void = () => {};
  const open = vi.fn(async (onEvent: (e: LiveEvent) => void) => {
    emit = onEvent;
    if (fails.shift()) throw new Error("socket");
    const s = new FakeSocket();
    socks.push(s);
    return s as unknown as WebSocket;
  });
  const link = connectLive(open, { onEvent: () => {}, onState: (s) => states.push(s), onReopen: reopened });
  return { socks, states, reopened, open, link, ready: () => emit({ type: "ready", audio: true }) };
}

afterEach(() => vi.useRealTimers());

describe("connectLive (spec B2)", () => {
  it("backs off exponentially with jitter and a cap", () => {
    expect(backoffMs(0, () => 1)).toBe(500);
    expect(backoffMs(3, () => 1)).toBe(4000);
    expect(backoffMs(20, () => 1)).toBe(15000);
    expect(backoffMs(2, () => 0)).toBe(1000);
  });

  it("reconnects after a drop, re-auths via a fresh open, and resumes", async () => {
    vi.useFakeTimers();
    const h = harness();
    const link = await h.link;
    expect(h.states).toEqual(["open"]);
    h.socks[0]!.drop(1006);
    expect(h.states.at(-1)).toBe("reconnecting");
    link.send("dropped while away");
    await vi.advanceTimersByTimeAsync(1000);
    expect(h.open).toHaveBeenCalledTimes(2);
    expect(h.states.at(-1)).toBe("open");
    expect(h.reopened).toHaveBeenCalledTimes(1);
    link.send("hello");
    expect(h.socks[1]!.sent).toEqual(["hello"]);
    expect(h.socks[0]!.sent).toEqual([]);
  });

  it("keeps retrying failed opens, then gives up after MAX_RETRIES", async () => {
    vi.useFakeTimers();
    const h = harness([false, ...Array<boolean>(MAX_RETRIES).fill(true)]);
    await h.link;
    h.socks[0]!.drop(1012);
    await vi.advanceTimersByTimeAsync(10 * 15000);
    expect(h.open).toHaveBeenCalledTimes(1 + MAX_RETRIES);
    expect(h.states.at(-1)).toBe("closed");
  });

  it("a ready event resets the backoff", async () => {
    vi.useFakeTimers();
    const h = harness([false, true, true]);
    await h.link;
    h.socks[0]!.drop(1006);
    await vi.advanceTimersByTimeAsync(20000);
    h.ready();
    h.socks[1]!.drop(1006);
    expect(h.open).toHaveBeenCalledTimes(4); // first + 2 failed retries + 1 that opened
    await vi.advanceTimersByTimeAsync(500); // reset: attempt 0 waits <= 500 ms (else >= 1 s)
    expect(h.open).toHaveBeenCalledTimes(5);
  });

  it("never retries a 4401 (not owner), a normal end, or after close()", async () => {
    vi.useFakeTimers();
    for (const code of [4401, 1000]) {
      const h = harness();
      await h.link;
      h.socks[0]!.drop(code);
      await vi.advanceTimersByTimeAsync(60000);
      expect(h.open).toHaveBeenCalledTimes(1);
      expect(h.states.at(-1)).toBe("closed");
    }
    const h = harness();
    (await h.link).close();
    h.socks[0]!.drop(1006);
    await vi.advanceTimersByTimeAsync(60000);
    expect(h.open).toHaveBeenCalledTimes(1);
  });

  it("rejects when the first open fails (page shows unreachable)", async () => {
    await expect(harness([true]).link).rejects.toThrow("socket");
  });
});

describe("mergeFeed", () => {
  const c = (id: string, at: string, status: FeedClaim["status"] = "checking"): FeedClaim => ({
    id, text: id, status, card_id: null, verdict: null, matched: false, latency_ms: null, created_at: at,
  });
  it("updates by id and keeps newest first", () => {
    const out = mergeFeed([c("a", "2026-10-15T10:00:00Z")], [c("a", "2026-10-15T10:00:00Z", "proved"), c("b", "2026-10-15T10:01:00Z")]);
    expect(out.map((x) => [x.id, x.status])).toEqual([["b", "checking"], ["a", "proved"]]);
  });
});

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

describe("pollRetry", () => {
  it("stops only on 404 and backs off on anything else", () => {
    expect(pollRetry(404, 0)).toBeNull();
    expect(pollRetry(503, 0, () => 1)).toBe(500);
    expect(pollRetry(null, 2, () => 1)).toBe(2000); // network error: keep polling
    expect(pollRetry(500, 40, () => 1)).toBe(15_000); // capped
  });
});
