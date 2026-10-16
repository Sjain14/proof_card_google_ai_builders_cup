// Typed client for the Proof Card API (backend/app/main.py). Same origin in prod via
// Firebase Hosting rewrites, Vite proxy in dev.
import { idToken } from "./auth";

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

// Clip upload (fallback when tab audio can't be captured). Goes straight to Cloud Run like
// the live socket (VITE_LIVE_ORIGIN): a long clip outlasts the Hosting rewrite timeout.
export async function uploadClip(
  sessionId: string,
  file: File,
  timed = false,
): Promise<{ sentences: number; events: unknown[] }> {
  const base = (import.meta.env.VITE_LIVE_ORIGIN as string | undefined) ?? "";
  const body = new FormData();
  body.append("file", file);
  const headers = new Headers();
  const token = await idToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${base}/api/sessions/${encodeURIComponent(sessionId)}/clip${timed ? "?timed=true" : ""}`, { method: "POST", body, headers });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new ApiError(res.status, errorText(res.status, err.detail));
  }
  return (await res.json()) as { sentences: number; events: unknown[] };
}

export const shareUrl = (cardId: string) => `${location.origin}/v/${cardId}`;
