import { useState } from "react";
import { shareUrl, type Card, type ClaimView } from "../api";
import { domain } from "../verdict";
import { VerdictPill } from "./VerdictPill";

export function CardTile({ claim, card }: { claim: ClaimView; card: Card | undefined }) {
  const [copied, setCopied] = useState(false);
  const pending = claim.status === "queued" || claim.status === "checking";

  if (pending) {
    return (
      <article className="tile pending" aria-busy="true">
        <span className="pill v-checking">
          <span className="spin" aria-hidden="true" /> Checking sources…
        </span>
        <p className="tile-claim">“{claim.text}”</p>
      </article>
    );
  }

  if (claim.status === "failed" || !claim.card_id) {
    return (
      <article className="tile">
        <span className="pill v-unknown">? Couldn't check</span>
        <p className="tile-claim">“{claim.text}”</p>
        <p className="tile-why muted">No source we could fetch backed or refuted this. We show that instead of guessing.</p>
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
        <span className="badge">{claim.source === "live" ? "LIVE" : "PREBUNKED"}</span>
      </div>
      <p className="tile-claim">“{card?.claim ?? claim.text}”</p>
      {card && (
        <>
          <p className="tile-why">{card.explanation}</p>
          <p className="tile-meta">
            {card.sources.map((s) => domain(s.url)).filter((d, i, a) => a.indexOf(d) === i).slice(0, 2).join(" · ")}
            {" · "}support {card.support_score.toFixed(2)}
          </p>
        </>
      )}
      <div className="tile-actions">
        <a className="btn small" href={url} target="_blank" rel="noopener">
          Proof
        </a>
        <button className="btn small ghost" onClick={() => void copy()}>
          {copied ? "Copied" : "Copy link"}
        </button>
        <a
          className="btn small ghost"
          href={`https://t.me/share/url?url=${encodeURIComponent(url)}`}
          target="_blank"
          rel="noopener"
        >
          Telegram
        </a>
        <a className="btn small ghost" href={`${url}.png`} download={`proof-card-${claim.card_id}.png`}>
          PNG
        </a>
      </div>
    </article>
  );
}
