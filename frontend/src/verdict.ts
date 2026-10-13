import type { ClaimStatus, Verdict } from "./api";

// Copy + colours from context/05_UI_UX.md §3. Never colour only: word + icon always.
export const VERDICT: Record<Verdict, { en: string; hi: string; icon: string; cls: string }> = {
  TRUE: { en: "True", hi: "सही", icon: "✓", cls: "v-true" },
  MISLEADING: { en: "Misleading", hi: "भ्रामक", icon: "◐", cls: "v-mislead" },
  FALSE: { en: "False", hi: "गलत", icon: "✕", cls: "v-false" },
  UNVERIFIABLE: { en: "Not enough proof", hi: "पुख्ता सबूत नहीं", icon: "?", cls: "v-unknown" },
};

export function progress(counts: Partial<Record<ClaimStatus, number>>): { done: number; total: number } {
  const n = (k: ClaimStatus) => counts[k] ?? 0;
  const done = n("proved") + n("failed");
  return { done, total: done + n("queued") + n("checking") };
}

export function domain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
