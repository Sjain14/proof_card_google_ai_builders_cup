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
export async function captureTabAudio(ws: WebSocket, onEnd: () => void): Promise<Capture> {
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
    if (ws.readyState === WebSocket.OPEN) ws.send(m.data);
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
