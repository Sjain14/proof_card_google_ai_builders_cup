// Typed client for the Proof Card API (backend/app/main.py). Same origin in prod via
// Firebase Hosting rewrites, Vite proxy in dev.
import { idToken } from "./auth";
import { pollRetry } from "./live";

export type Verdict = "TRUE" | "MISLEADING" | "FALSE" | "UNVERIFIABLE";
export type ClaimStatus = "queued" | "checking" | "proved" | "failed";

export interface ClaimView {
  id: string;
  text: string;
  lang: string;
  source: "predicted" | "live";
  status: ClaimStatus;
  card_id: string | null;
  verdict: Verdict | null;
  matched_claim_id?: string | null;
  t_offset_s?: number | null; // replay: second in the YouTube video
  matched?: boolean;
}

export interface SessionView {
  id: string;
  topic: string;
  speaker: string;
  status: string;
  youtube_url: string | null;
  public_view: boolean;
  claims: ClaimView[];
  counts: Record<ClaimStatus, number>;
}

export interface Source {
  url: string;
  title: string;
  snippet: string;
  snapshot_sha256: string;
  fetched_at: string;
}

export interface Card {
  claim: string;
  verdict: Verdict;
  explanation: string;
  sources: Source[];
  support_score: number;
  card_sha256: string;
  // Google Search suggestion for the grounded explanation; shown via the sandboxed frame.
  search_suggestion_html?: string | null;
  created_at: string;
}

export interface PrebunkInput {
  topic: string;
  speaker?: string;
  youtube_url?: string;
  context_links?: string[];
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}, auth = false): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (auth) {
    const token = await idToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(path, { ...init, headers });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new ApiError(res.status, errorText(res.status, body.detail));
  }
  return (await res.json()) as T;
}

export function errorText(status: number, detail: unknown): string {
  if (status === 401) return "Please sign in again.";
  if (status === 429) return "Too many requests, wait a moment.";
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string; loc?: unknown[] };
    const field = first.loc?.slice(1).join(".") ?? "";
    return `${field ? field + ": " : ""}${(first.msg ?? "invalid").replace(/^Value error, /, "")}`;
  }
  return typeof detail === "string" ? detail : `Something went wrong (${status}).`;
}

export const api = {
  createBrief: (input: PrebunkInput) =>
    call<{ session_id: string }>("/api/prebunk", { method: "POST", body: JSON.stringify(input) }, true),
  session: (id: string) => call<SessionView>(`/api/sessions/${encodeURIComponent(id)}`, {}, true),
  card: (id: string) => call<Card>(`/api/cards/${encodeURIComponent(id)}`),
  telegramLink: (id: string) =>
    call<{ url: string }>(`/api/sessions/${encodeURIComponent(id)}/telegram-link`, { method: "POST" }, true),
  share: (id: string, on: boolean) =>
    call<{ public_view: boolean }>(
      `/api/sessions/${encodeURIComponent(id)}/share`,
      { method: "POST", body: JSON.stringify({ public_view: on }) },
      true,
    ),
  feed: (id: string, since: string | null) =>
    call<FeedView>(`/api/sessions/${encodeURIComponent(id)}/feed${since ? `?since=${encodeURIComponent(since)}` : ""}`),
};

/** Public read only stream for /watch/:id (backend FeedView). No owner data. */
export interface FeedClaim {
  id: string;
  text: string;
  status: ClaimStatus;
  card_id: string | null;
  verdict: Verdict | null;
  matched: boolean;
  latency_ms: number | null;
  created_at: string;
}

export interface FeedView {
  id: string;
  topic: string;
  speaker: string;
  status: string;
  claims: FeedClaim[];
  cursor: string;
}

/** Merge a poll into what we have: keyed by id, newest heard first. */
export function mergeFeed(have: FeedClaim[], got: FeedClaim[]): FeedClaim[] {
  const m = new Map(have.map((c) => [c.id, c]));
  for (const c of got) m.set(c.id, c);
  return [...m.values()].sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export const watchUrl = (sessionId: string) => `${location.origin}/watch/${sessionId}`;

export const CLIP_MAX_BYTES = 20 * 1024 * 1024;

export interface ClipJob {
  state: "queued" | "running" | "done" | "failed";
  timed: boolean;
  sentences: number | null;
  done: number;
  events: unknown[];
  error: string;
}

const CLIP_POLL_MS = 3000;

// Clip upload (fallback when tab audio can't be captured). Goes straight to Cloud Run like
// the live socket (VITE_LIVE_ORIGIN). The server answers at once (202) and works the clip
// in the background; we poll its progress. A 9 min clip outlived one request (16 Oct).
export async function uploadClip(
  sessionId: string,
  file: File,
  timed = false,
  onProgress?: (done: number, total: number | null) => void,
): Promise<{ sentences: number; events: unknown[] }> {
  const base = (import.meta.env.VITE_LIVE_ORIGIN as string | undefined) ?? "";
  const url = `${base}/api/sessions/${encodeURIComponent(sessionId)}/clip`;
  const auth = async () => {
    const headers = new Headers();
    const token = await idToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return headers;
  };
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${url}${timed ? "?timed=true" : ""}`, { method: "POST", body, headers: await auth() });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new ApiError(res.status, errorText(res.status, err.detail));
  }
  let failures = 0;
  for (;;) {
    let job: ClipJob | null = null;
    let status: number | null = null;
    try {
      const r = await fetch(url, { headers: await auth() });
      if (r.ok) job = (await r.json()) as ClipJob;
      else status = r.status;
    } catch {
      status = null; // network blip
    }
    if (job) {
      failures = 0;
      if (job.state === "done") return { sentences: job.sentences ?? 0, events: job.events };
      if (job.state === "failed") throw new ApiError(502, job.error || errorText(502, undefined));
      onProgress?.(job.done, job.sentences);
    }
    const wait = job ? CLIP_POLL_MS : pollRetry(status, failures++);
    if (wait === null) throw new ApiError(404, errorText(404, undefined));
    await new Promise((ok) => setTimeout(ok, Math.max(wait, CLIP_POLL_MS)));
  }
}

export const shareUrl = (cardId: string) => `${location.origin}/v/${cardId}`;
