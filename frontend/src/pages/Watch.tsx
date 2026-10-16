import { useEffect, useState } from "react";
import { onePerCard } from "../verdict";
import { api, ApiError, mergeFeed, type Card, type FeedClaim } from "../api";
import { CardTile } from "../components/CardTile";
import { t } from "../i18n";

const POLL_MS = 2000;

// Read only viewer link (spec §5, B1): no audio, no sign in, works on any phone.
// Polls the public feed (backend session_feed); paused while the tab is hidden.
export function Watch({ id }: { id: string }) {
  const [topic, setTopic] = useState("");
  const [claims, setClaims] = useState<FeedClaim[]>([]);
  const [cards, setCards] = useState<Record<string, Card>>({});
  const [note, setNote] = useState("");

  useEffect(() => {
    let since: string | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let dead = false;
    const tick = async () => {
      if (!document.hidden) {
        try {
          const f = await api.feed(id, since);
          since = f.cursor;
          setTopic(f.topic);
          setClaims((have) => mergeFeed(have, f.claims));
          setNote("");
        } catch (e) {
          if (e instanceof ApiError && e.status === 404) return setNote(t("watch.closed")); // stop polling
          setNote(t("watch.retrying"));
        }
      }
      if (!dead) timer = setTimeout(() => void tick(), POLL_MS);
    };
    void tick();
    return () => {
      dead = true;
      clearTimeout(timer);
    };
  }, [id]);

  // Cards are immutable: fetch each once.
  useEffect(() => {
    for (const c of claims) {
      const cid = c.card_id;
      if (cid && !cards[cid]) void api.card(cid).then((card) => setCards((m) => ({ ...m, [cid]: card })), () => {});
    }
  }, [claims, cards]);

  return (
    <section className="live watch">
      <div className="brief-head">
        <div>
          <p className="eyebrow">{t("watch.eyebrow")}</p>
          <h1>{topic || t("live.loading")}</h1>
        </div>
      </div>
      {note && <p className="note" role="status">{note}</p>}
      <div className="feed" aria-live="polite">
        {claims.length === 0 && !note && (
          <div className="tile pending feed-empty"><p className="muted">{t("live.empty")}</p></div>
        )}
        {onePerCard(claims, (c) => c.card_id).map((c) => (
          <div className="feed-item" key={c.id}>
            <div className="feed-meta">
              <span className={`badge ${c.matched ? "b-pre" : "b-live"}`}>{c.matched ? "PREBUNKED" : "LIVE"}</span>
              {c.latency_ms !== null && <span className="latency">{c.latency_ms} ms</span>}
            </div>
            <CardTile
              claim={{ id: c.id, text: c.text, lang: "en", source: "live", status: c.status, card_id: c.card_id, verdict: c.verdict }}
              card={c.card_id ? cards[c.card_id] : undefined}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
