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
}

export interface SessionView {
  id: string;
  topic: string;
  speaker: string;
  status: string;
  youtube_url: string | null;
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
};

export const shareUrl = (cardId: string) => `${location.origin}/v/${cardId}`;
