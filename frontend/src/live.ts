// Live bridge client: tab audio -> 16 kHz PCM16 frames -> backend websocket (/api/live/:id).
// Capture: https://developer.mozilla.org/docs/Web/API/MediaDevices/getDisplayMedia
// Worklet: https://developer.mozilla.org/docs/Web/API/AudioWorkletNode
// Format the backend relays to the Gemini Live API: raw PCM16, 16 kHz mono, ~100 ms chunks.
import { idToken } from "./auth";
import type { Verdict } from "./api";

// Why a heard line produced no card: the server always says, never silence.
export type SkipReason = "not_checkable" | "repeat" | "error";

export type LiveEvent =
  | { type: "ready"; audio: boolean }
  | { type: "heard"; text: string }
  | { type: "match"; claim_id: string; text: string; card_id: string; verdict: Verdict | null; similarity: number; latency_ms: number }
  | { type: "checking"; claim_id: string; text: string }
  | { type: "proved"; claim_id: string; text: string; card_id: string; verdict: Verdict | null; latency_ms: number }
  | { type: "failed"; claim_id: string; text: string }
  | { type: "skipped"; text: string; reason: SkipReason }
  | { type: "error"; code: string };

const RATE = 16000;
const FRAME = 1600; // 100 ms at 16 kHz

// Firebase Hosting rewrites don't carry websockets, so in prod the socket goes straight to
// the Cloud Run URL (VITE_LIVE_ORIGIN, externals/E09). Dev: same origin via the Vite proxy.
export function liveUrl(sessionId: string): string {
  const base = import.meta.env.VITE_LIVE_ORIGIN || location.origin;
  return `${base.replace(/^http/, "ws")}/api/live/${encodeURIComponent(sessionId)}`;
}

export async function openLive(sessionId: string, onEvent: (e: LiveEvent) => void): Promise<WebSocket> {
  const ws = new WebSocket(liveUrl(sessionId));
  ws.binaryType = "arraybuffer";
  const token = (await idToken()) ?? "";
  await new Promise<void>((ok, fail) => {
    ws.onopen = () => ok();
    ws.onerror = () => fail(new Error("socket"));
  });
  ws.send(JSON.stringify({ type: "auth", token })); // first message, never in the URL
  ws.onmessage = (m) => onEvent(JSON.parse(String(m.data)) as LiveEvent);
  return ws;
}

export type LinkState = "open" | "reconnecting" | "closed";

export interface LiveLink {
  send: (data: string | ArrayBuffer) => void; // dropped while reconnecting (live audio, no replay)
  close: () => void;
}

/** Exponential backoff with full jitter: 0.5 s, 1 s, 2 s ... capped at 15 s. */
export function backoffMs(attempt: number, rand: () => number = Math.random): number {
  return Math.round(Math.min(15_000, 500 * 2 ** attempt) * (0.5 + rand() / 2));
}

export const MAX_RETRIES = 8;

/** A failed poll: stop only when the thing is gone (404); anything else (network blip,
 *  503 during a deploy) keeps polling with backoff. Brief.tsx stopped for good after one
 *  failed load (demo run, 16 Oct 2026). */
export function pollRetry(status: number | null, failures: number, rand: () => number = Math.random): number | null {
  return status === 404 ? null : backoffMs(Math.min(failures, 5), rand);
}

/**
 * A live socket that survives drops (spec B2). Rejects only if the FIRST open fails.
 * After that an unexpected close retries with backoff, re-authenticating every time
 * (`open` fetches a fresh ID token), and calls `onReopen` so the page reloads the session
 * from GET /api/sessions/:id (cards made while we were away are in Firestore).
 * 4401 (not the owner) and 1000 (normal end) are final.
 */
export async function connectLive(
  open: (onEvent: (e: LiveEvent) => void) => Promise<WebSocket>,
  h: { onEvent: (e: LiveEvent) => void; onState: (s: LinkState, code?: number) => void; onReopen: () => void },
): Promise<LiveLink> {
  let ws: WebSocket | null = null;
  let stopped = false;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const onEvent = (e: LiveEvent) => {
    if (e.type === "ready") attempt = 0; // healthy again: next drop starts from 0.5 s
    h.onEvent(e);
  };
  const retry = (code?: number) => {
    if (stopped) return;
    if (attempt >= MAX_RETRIES) return h.onState("closed", code);
    h.onState("reconnecting", code);
    timer = setTimeout(() => void attach(true), backoffMs(attempt++));
  };
  const attach = async (again: boolean) => {
    let sock: WebSocket;
    try {
      sock = await open(onEvent);
    } catch (err) {
      if (!again) throw err;
      return retry();
    }
    if (stopped) return sock.close();
    ws = sock;
    sock.onclose = (c) => {
      ws = null;
      if (stopped) return;
      if (c.code === 4401 || c.code === 1000) {
        stopped = true;
        return h.onState("closed", c.code);
      }
      retry(c.code);
    };
    h.onState("open");
    if (again) h.onReopen();
  };
  await attach(false);
  return {
    send: (data) => {
      if (ws && ws.readyState === 1) ws.send(data); // 1 = OPEN
    },
    close: () => {
      stopped = true;
      clearTimeout(timer);
      ws?.close();
    },
  };
}

// Runs on the audio thread: Float32 at 16 kHz in, Int16 frames of 100 ms out.
const WORKLET = `
class Pcm16 extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Int16Array(${FRAME}); this.n = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      const s = Math.max(-1, Math.min(1, ch[i]));
      this.buf[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.n === ${FRAME}) { this.port.postMessage(this.buf.buffer, [this.buf.buffer]); this.buf = new Int16Array(${FRAME}); this.n = 0; }
    }
    return true;
  }
}
registerProcessor("pcm16", Pcm16);`;

export interface Capture {
  stop: () => void;
}

/** Ask for this tab's audio (user picks the tab and ticks "share tab audio"). */
export async function captureTabAudio(link: Pick<LiveLink, "send">, onEnd: () => void): Promise<Capture> {
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true, // Chrome requires video to offer tab audio; we drop it at once
    audio: { echoCancellation: false, noiseSuppression: false },
    preferCurrentTab: true,
  } as DisplayMediaStreamOptions);
  stream.getVideoTracks().forEach((t) => t.stop());
  const track = stream.getAudioTracks()[0];
  if (!track) {
    stream.getTracks().forEach((t) => t.stop());
    throw new Error("no-audio");
  }
  const ctx = new AudioContext({ sampleRate: RATE }); // the browser resamples for us
  const url = URL.createObjectURL(new Blob([WORKLET], { type: "text/javascript" }));
  await ctx.audioWorklet.addModule(url);
  URL.revokeObjectURL(url);
  const node = new AudioWorkletNode(ctx, "pcm16");
  node.port.onmessage = (m: MessageEvent<ArrayBuffer>) => {
    link.send(m.data);
  };
  const src = ctx.createMediaStreamSource(new MediaStream([track]));
  src.connect(node); // not connected to the speakers: the video already plays its sound
  const stop = () => {
    track.stop();
    src.disconnect();
    node.disconnect();
    void ctx.close();
  };
  track.onended = () => {
    stop();
    onEnd();
  };
  return { stop };
}

/** YouTube watch / share / shorts / embed link -> video id, else null. */
export function youtubeId(url: string): string | null {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\.|^m\./, "");
    if (host === "youtu.be") return u.pathname.slice(1, 12) || null;
    if (host !== "youtube.com" && host !== "youtube-nocookie.com") return null;
    const v = u.searchParams.get("v") ?? u.pathname.match(/^\/(?:embed|shorts|live)\/([\w-]{11})/)?.[1];
    return v && /^[\w-]{11}$/.test(v) ? v : null;
  } catch {
    return null;
  }
}

// ---------- replay: YouTube IFrame Player API ----------
// https://developers.google.com/youtube/iframe_api_reference
// Cards of a timed clip carry t_offset_s; the Live page polls getCurrentTime() and shows
// every card whose second has been reached, so seek / pause / rewind stay in sync.

export interface YtPlayer {
  getCurrentTime(): number;
  playVideo(): void;
  destroy(): void;
}

interface YtNamespace {
  Player: new (el: HTMLElement, opts: Record<string, unknown>) => YtPlayer;
}

let ytReady: Promise<YtNamespace> | null = null;

export function loadYouTube(): Promise<YtNamespace> {
  const w = window as unknown as { YT?: YtNamespace; onYouTubeIframeAPIReady?: () => void };
  if (w.YT?.Player) return Promise.resolve(w.YT);
  ytReady ??= new Promise((resolve, reject) => {
    w.onYouTubeIframeAPIReady = () => (w.YT ? resolve(w.YT) : reject(new Error("youtube")));
    const tag = document.createElement("script");
    tag.src = "https://www.youtube.com/iframe_api";
    tag.onerror = () => reject(new Error("youtube"));
    document.head.appendChild(tag);
  });
  return ytReady;
}

/** Live claims of a timed clip that the video has reached, newest first. */
export function replayDue<T extends { source: string; t_offset_s?: number | null }>(claims: T[], now: number): T[] {
  return claims
    .filter((c) => c.source === "live" && c.t_offset_s != null && c.t_offset_s <= now)
    .sort((a, b) => (b.t_offset_s ?? 0) - (a.t_offset_s ?? 0));
}

/** Every live claim already checked, newest first: what the page shows before Replay
 * (it showed "0 checked live" on a finished session until Replay, review 17 Oct). */
export function pastLive<T extends { source: string; t_offset_s?: number | null }>(claims: T[]): T[] {
  return claims
    .filter((c) => c.source === "live")
    .sort((a, b) => (b.t_offset_s ?? 0) - (a.t_offset_s ?? 0));
}

/** Poster shown while the replay player loads, so the stage is never a blank box. */
export function ytPoster(id: string): string {
  return `https://i.ytimg.com/vi/${id}/hqdefault.jpg`;
}

export function clock(s: number): string {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${r.toString().padStart(2, "0")}`;
}
