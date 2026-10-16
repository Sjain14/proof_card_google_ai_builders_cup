import { useState } from "react";
import { shareUrl, type Card, type ClaimView } from "../api";
import { domain } from "../verdict";
import { VerdictPill } from "./VerdictPill";
import { t } from "../i18n";

// showSource=false where the feed row already shows PREBUNKED / LIVE above the card
// (live + watch pages): the tile's own badge said LIVE under a PREBUNKED row. In a brief
// every card is prebunked, so only a LIVE one is marked (no badge repeated on each tile).
/** Telegram share: the message arrives already written (verdict + claim), link attached. */
export function tgText(verdict: string | null | undefined, claim: string): string {
  const v = verdict ? t(`verdict.${verdict as "TRUE"}`).toUpperCase() : "";
  const short = claim.length > 140 ? `${claim.slice(0, 137)}…` : claim;
  return `${v ? `${v}: ` : ""}“${short}” · Proof Card`;
}

export function CardTile({ claim, card, showSource = true }: { claim: ClaimView; card: Card | undefined; showSource?: boolean }) {
  const [copied, setCopied] = useState(false);
  const pending = claim.status === "queued" || claim.status === "checking";

  if (pending) {
    return (
      <article className="tile pending" aria-busy="true">
        <span className="pill v-checking">
          <span className="spin" aria-hidden="true" /> {t("tile.checking")}
        </span>
        <p className="tile-claim">“{claim.text}”</p>
      </article>
    );
  }

  if (claim.status === "failed" || !claim.card_id) {
    return (
      <article className="tile">
        <span className="pill v-unknown">? {t("tile.couldnt")}</span>
        <p className="tile-claim">“{claim.text}”</p>
        <p className="tile-why muted">{t("tile.noSource")}</p>
      </article>
    );
  }

  const url = shareUrl(claim.card_id);
  const copy = async () => {
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <article className="tile stamped">
      <div className="tile-top">
        <VerdictPill verdict={card?.verdict ?? claim.verdict ?? "UNVERIFIABLE"} />
        {showSource && claim.source === "live" && <span className="badge">{t("tile.live")}</span>}
      </div>
      <p className="tile-claim">“{card?.claim ?? claim.text}”</p>
      {card && (
        <>
          <p className="tile-why">{card.explanation}</p>
          {card.search_suggestion_html && (
            // Grounding terms: Google's suggestion chips stay visible next to the grounded
            // text, unmodified. Its own document + sandbox; a tap opens Google directly.
            <iframe
              className="gsugg"
              src={`/api/cards/${encodeURIComponent(claim.card_id)}/search-suggestion`}
              sandbox="allow-popups allow-popups-to-escape-sandbox"
              title="Google Search suggestions"
              referrerPolicy="no-referrer"
              loading="lazy"
            />
          )}
          <p className="tile-meta">
            {card.sources.map((s) => domain(s.url)).filter((d, i, a) => a.indexOf(d) === i).slice(0, 2).join(" · ")}
            {" · "}{t("tile.support")} {card.support_score.toFixed(2)}
          </p>
        </>
      )}
      <div className="tile-actions">
        <a className="btn small" href={url} target="_blank" rel="noopener">
          {t("tile.proof")}
        </a>
        <button className="btn small ghost" onClick={() => void copy()}>
          {copied ? t("tile.copied") : t("tile.copy")}
        </button>
        <a
          className="btn small ghost"
          href={`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(tgText(card?.verdict ?? claim.verdict, card?.claim ?? claim.text))}`}
          target="_blank"
          rel="noopener"
        >
          {t("tile.tg")}
        </a>
        <a className="btn small ghost" href={`${url}.png`} download={`proof-card-${claim.card_id}.png`}>
          PNG
        </a>
      </div>
    </article>
  );
}
