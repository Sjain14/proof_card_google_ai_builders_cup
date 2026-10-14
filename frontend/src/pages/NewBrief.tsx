import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import { signIn, type SignedIn } from "../auth";
import { navigate } from "../router";
import { t } from "../i18n";

const SAMPLE = {
  topic: "Union Budget speech: fuel prices, digital India, languages and population",
  speaker: "Finance Minister",
};

export function NewBrief({ user }: { user: SignedIn | null | undefined }) {
  const [topic, setTopic] = useState("");
  const [speaker, setSpeaker] = useState("");
  const [youtube, setYoutube] = useState("");
  const [links, setLinks] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user === null) {
    return (
      <section className="panel narrow center">
        <h1>{t("new.signInH")}</h1>
        <p className="muted">{t("new.signInBody")}</p>
        <button className="btn" onClick={() => void signIn()}>
          {t("new.signInBtn")}
        </button>
      </section>
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const context_links = links
        .split(/\s+/)
        .map((l) => l.trim())
        .filter(Boolean)
        .slice(0, 5);
      const { session_id } = await api.createBrief({
        topic: topic.trim(),
        ...(speaker.trim() && { speaker: speaker.trim() }),
        ...(youtube.trim() && { youtube_url: youtube.trim() }),
        ...(context_links.length && { context_links }),
      });
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
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            maxLength={500}
            rows={3}
            required
            placeholder={t("new.topicPh")}
          />
        </label>
        <label>
          {t("new.speaker")}
          <input value={speaker} onChange={(e) => setSpeaker(e.target.value)} maxLength={200} />
        </label>
        <label>
          {t("new.youtube")}
          <input
            value={youtube}
            onChange={(e) => setYoutube(e.target.value)}
            type="url"
            inputMode="url"
            placeholder="https://youtu.be/…"
          />
        </label>
        <label>
          {t("new.links")} <span className="muted">{t("new.linksHint")}</span>
          <input value={links} onChange={(e) => setLinks(e.target.value)} inputMode="url" />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="row">
          <button className="btn" disabled={busy || !topic.trim()}>
            {busy ? t("new.starting") : t("new.generate")}
          </button>
          <button
            type="button"
            className="link"
            onClick={() => {
              setTopic(SAMPLE.topic);
              setSpeaker(SAMPLE.speaker);
            }}
          >
            {t("new.sample")}
          </button>
        </div>
      </form>
    </section>
  );
}
