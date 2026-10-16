import { useEffect, useState } from "react";
import { api, ApiError, type Card, type SessionView } from "../api";
import type { SignedIn } from "../auth";
import { CardTile } from "../components/CardTile";
import { navigate } from "../router";
import { pollRetry } from "../live";
import { progress } from "../verdict";
import { t } from "../i18n";

const POLL_MS = 1500;

export function Brief({ id, user }: { id: string; user: SignedIn | null | undefined }) {
  const [session, setSession] = useState<SessionView | null>(null);
  const [cards, setCards] = useState<Record<string, Card>>({});
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  // Poll the session until every claim is proved or failed. shortcut: polling, not a
  // Firestore listener; fine for a 12 claim brief, switch to onSnapshot for live mode.
  useEffect(() => {
    if (!user) return;
    let alive = true;
    let timer = 0;
    let failures = 0;
    const tick = async () => {
      try {
        const s = await api.session(id);
        if (!alive) return;
        failures = 0;
        setNote("");
        setSession(s);
        const p = progress(s.counts);
        if (s.status !== "failed" && (p.total === 0 || p.done < p.total)) timer = window.setTimeout(tick, POLL_MS);
      } catch (err) {
        if (!alive) return;
        const wait = pollRetry(err instanceof ApiError ? err.status : null, failures++);
        if (wait === null) return setError(t("brief.none"));
        setNote(t("brief.retrying")); // soft: keep what we have on screen and keep polling
        timer = window.setTimeout(tick, wait);
      }
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [id, user]);

  // Cards are immutable: fetch each once.
  useEffect(() => {
    const missing = (session?.claims ?? []).filter((c) => c.card_id && !cards[c.card_id]);
    for (const c of missing) {
      const cid = c.card_id!;
      void api.card(cid).then((card) => setCards((m) => ({ ...m, [cid]: card })), () => {});
    }
  }, [session, cards]);

  if (error) return <section className="panel narrow center"><h1>{error}</h1></section>;
  if (!session) return <section className="panel narrow center"><p className="muted">{note || t("brief.loading")}</p></section>;
  if (session.status === "failed" && session.claims.length === 0) return <section className="panel narrow center"><h1>{t("brief.failed")}</h1></section>;

  const { done, total } = progress(session.counts);
  const pct = total ? Math.round((done / total) * 100) : 0;

  return (
    <section className="brief">
      <div className="brief-head">
        <div>
          <p className="eyebrow">{t("brief.eyebrow")}{session.speaker && ` · ${session.speaker}`}</p>
          <h1>{session.topic}</h1>
        </div>
        <div className="progress" aria-live="polite">
          <span>
            {total === 0 ? t("brief.predicting") : done < total ? t("brief.progress", { done, total }) : t("brief.ready", { total })}
          </span>
          {note && <span className="muted">{note}</span>}
          {total > 0 && (done === total || session.status === "ready") && (
            <>
              <span className="muted small">{t("brief.next")}</span>
              <button className="btn small" onClick={() => navigate(`/s/${id}/live`)}>
                {t("brief.goLive")}
              </button>
            </>
          )}
          <div className="bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <i style={{ width: `${total ? pct : 8}%` }} className={total === 0 ? "indeterminate" : ""} />
          </div>
        </div>
      </div>
      <div className="grid">
        {session.claims.map((c) => (
          <CardTile key={c.id} claim={c} card={c.card_id ? cards[c.card_id] : undefined} />
        ))}
        {total === 0 && [0, 1, 2].map((i) => <div key={i} className="tile skeleton" />)}
      </div>
    </section>
  );
}
