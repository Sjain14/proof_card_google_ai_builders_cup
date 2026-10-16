// The judge's sample: a real, recorded Trump clip (euronews, 2 min 23 s) with checkable
// claims (eight wars, the Nobel). One click fills the whole form; on the live page one
// click sends the same clip's audio (served from /samples) so nobody hunts for a file.

export const SAMPLE_VIDEO_ID = "swR1RGScmvU";

export const SAMPLE = {
  youtube: `https://www.youtube.com/watch?v=${SAMPLE_VIDEO_ID}`,
  topic: "“I settled eight wars”: Trump says he deserves the Nobel Peace Prize",
  speaker: "Donald Trump",
  links: "https://www.nobelprize.org/prizes/peace/",
} as const;

export const SAMPLE_CLIP = "/samples/trump-nobel.mp3";

export function isSampleVideo(id: string | null | undefined): boolean {
  return id === SAMPLE_VIDEO_ID;
}

/** /new?sample=trump opens the form already filled (the how-to page links here). */
export function wantsSample(search: string): boolean {
  return new URLSearchParams(search).get("sample") === "trump";
}
