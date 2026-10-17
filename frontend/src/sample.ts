// The judge's sample: a real, recorded 2 min 23 s news clip (euronews) with checkable
// claims. The UI copy never names a politician (Team lead, 17 Oct: a Google competition must
// not read as targeting one leader); the clip's own topic/speaker only appear once filled. One click fills the whole form; on the live page one
// click sends the same clip's audio (served from /samples) so nobody hunts for a file.

export const SAMPLE_VIDEO_ID = "swR1RGScmvU";

export const SAMPLE = {
  youtube: `https://www.youtube.com/watch?v=${SAMPLE_VIDEO_ID}`,
  topic: "“I settled eight wars”: Trump says he deserves the Nobel Peace Prize",
  speaker: "Donald Trump",
  links: "https://www.nobelprize.org/prizes/peace/",
} as const;

export const SAMPLE_CLIP = "/samples/sample-clip.mp3";

export function isSampleVideo(id: string | null | undefined): boolean {
  return id === SAMPLE_VIDEO_ID;
}

/** /new?sample=1 (or the old ?sample=trump links) opens the form already filled (the how-to page links here). */
export function wantsSample(search: string): boolean {
  const v = new URLSearchParams(search).get("sample");
  return v === "1" || v === "trump";
}
