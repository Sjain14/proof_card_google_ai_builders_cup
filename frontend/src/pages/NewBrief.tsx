import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import { signIn, signInGuest, type SignedIn } from "../auth";
import { navigate } from "../router";
import { t } from "../i18n";

import { useAppStore } from "../store";
import { SAMPLE, wantsSample } from "../sample";

export function NewBrief({ user }: { user: SignedIn | null | undefined }) {
  const draft = useAppStore((s) => s.draft);
  const setDraft = useAppStore((s) => s.setDraft);
  const clearDraft = useAppStore((s) => s.clearDraft);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sampled, setSampled] = useState(false);
  const more = useRef<HTMLDetailsElement | null>(null);
  const fillSample = () => {
    setDraft({ youtube: SAMPLE.youtube, topic: SAMPLE.topic, speaker: SAMPLE.speaker, links: SAMPLE.links });
    setSampled(true);
    if (more.current) more.current.open = true; // every filled field on screen
  };
  // /new?sample=trump (from the how-to page): open already filled.
  useEffect(() => {
    if (user && wantsSample(location.search)) {
      fillSample();
      history.replaceState(null, "", "/new");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  if (user === null) {
    return (
      <section className="panel narrow center">
        <h1>{t("new.signInH")}</h1>
        <p className="muted">{t("new.signInBody")}</p>
        <div style={{ display: "flex", gap: "10px", justifyContent: "center", flexWrap: "wrap" }}>
          <button className="btn" onClick={() => void signIn()}>
            {t("new.signInBtn")}
          </button>
          <button className="btn ghost" onClick={() => void signInGuest()}>
            {t("new.guestBtn")}
          </button>
        </div>
      </section>
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const context_links = draft.links
        .split(/\s+/)
        .map((l) => l.trim())
        .filter(Boolean)
        .slice(0, 5);
      const { session_id } = await api.createBrief({
        topic: draft.topic.trim(),
        ...(draft.speaker.trim() && { speaker: draft.speaker.trim() }),
        ...(draft.youtube.trim() && { youtube_url: draft.youtube.trim() }),
        ...(context_links.length && { context_links }),
      });
      clearDraft();
      navigate(`/s/${session_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("new.network"));
      setBusy(false);
    }
  }

  return (
    <section className="panel narrow">
      <div className="new-head">
        <div>
          <p className="eyebrow">{t("new.eyebrow")}</p>
          <h1>{t("new.h1")}</h1>
        </div>
        <button type="button" className="btn small ghost" onClick={fillSample}>
          {t("new.sample")}
        </button>
      </div>
      <form onSubmit={(e) => void submit(e)} className="form">
        <label>
          {t("new.youtube")} <span className="muted">{t("new.youtubeHint")}</span>
          <input
            value={draft.youtube}
            onChange={(e) => {
              setDraft({ youtube: e.target.value });
              setSampled(false);
            }}
            type="url"
            inputMode="url"
            placeholder="https://youtu.be/…"
            autoFocus
          />
        </label>
        <label>
          {t("new.topic")}{" "}
          <span className="req">{draft.youtube.trim() ? t("new.topicAuto") : t("new.required")}</span>
          <textarea
            value={draft.topic}
            onChange={(e) => setDraft({ topic: e.target.value })}
            maxLength={500}
            rows={2}
            required={!draft.youtube.trim()}
            placeholder={t("new.topicPh")}
          />
        </label>
        <details className="more" ref={more}>
          <summary>{t("new.more")}</summary>
          <label>
            {t("new.speaker")}
            <input
              value={draft.speaker}
              onChange={(e) => setDraft({ speaker: e.target.value })}
              maxLength={200}
            />
          </label>
          <label>
            {t("new.links")} <span className="muted">{t("new.linksHint")}</span>
            <input
              value={draft.links}
              onChange={(e) => setDraft({ links: e.target.value })}
              inputMode="url"
            />
          </label>
        </details>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {sampled && (
          <p className="note" role="status">
            {t("new.sampleNote")}
          </p>
        )}
        <div className="row">
          <button className="btn" disabled={busy || (!draft.topic.trim() && !draft.youtube.trim())}>
            {busy ? t("new.starting") : t("new.generate")}
          </button>
          <a
            className="link"
            href="/how"
            onClick={(e) => {
              e.preventDefault();
              navigate("/how");
            }}
          >
            {t("new.howLink")}
          </a>
        </div>
      </form>
      <div className="modes" aria-labelledby="modes-h">
        <p id="modes-h" className="vis-cap">{t("new.modesH")}</p>
        <div className="modes-grid">
          <p>
            <b>▶</b> {t("new.modeRec")}
          </p>
          <p>
            <span className="live-dot" aria-hidden="true" /> {t("new.modeLive")}
          </p>
        </div>
      </div>
    </section>
  );
}
