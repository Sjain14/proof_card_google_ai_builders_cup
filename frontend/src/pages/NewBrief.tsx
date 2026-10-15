import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import { signIn, signInGuest, type SignedIn } from "../auth";
import { navigate } from "../router";
import { t } from "../i18n";

import { useAppStore } from "../store";

const SAMPLE = {
  topic: "Union Budget speech: fuel prices, digital India, languages and population",
  speaker: "Finance Minister",
};

export function NewBrief({ user }: { user: SignedIn | null | undefined }) {
  const draft = useAppStore((s) => s.draft);
  const setDraft = useAppStore((s) => s.setDraft);
  const clearDraft = useAppStore((s) => s.clearDraft);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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
      <p className="eyebrow">{t("new.eyebrow")}</p>
      <h1>{t("new.h1")}</h1>
      <form onSubmit={(e) => void submit(e)} className="form">
        <label>
          {t("new.topic")} <span className="req">{t("new.required")}</span>
          <textarea
            value={draft.topic}
            onChange={(e) => setDraft({ topic: e.target.value })}
            maxLength={500}
            rows={3}
            required
            placeholder={t("new.topicPh")}
          />
        </label>
        <label>
          {t("new.speaker")}
          <input
            value={draft.speaker}
            onChange={(e) => setDraft({ speaker: e.target.value })}
            maxLength={200}
          />
        </label>
        <label>
          {t("new.youtube")}
          <input
            value={draft.youtube}
            onChange={(e) => setDraft({ youtube: e.target.value })}
            type="url"
            inputMode="url"
            placeholder="https://youtu.be/…"
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
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="row">
          <button className="btn" disabled={busy || !draft.topic.trim()}>
            {busy ? t("new.starting") : t("new.generate")}
          </button>
          <button
            type="button"
            className="link"
            onClick={() => {
              setDraft({ topic: SAMPLE.topic, speaker: SAMPLE.speaker });
            }}
          >
            {t("new.sample")}
          </button>
        </div>
      </form>
    </section>
  );
}
