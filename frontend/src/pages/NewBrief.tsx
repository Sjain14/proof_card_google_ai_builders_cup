import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import { signIn, type SignedIn } from "../auth";
import { navigate } from "../router";

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
        <h1>Sign in to create a brief</h1>
        <p className="muted">Briefs are private to you. Cards you share are public.</p>
        <button className="btn" onClick={() => void signIn()}>
          Sign in with Google
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
      setError(err instanceof ApiError ? err.message : "Network error, try again.");
      setBusy(false);
    }
  }

  return (
    <section className="panel narrow">
      <p className="eyebrow">New brief</p>
      <h1>What's the speech about?</h1>
      <form onSubmit={(e) => void submit(e)} className="form">
        <label>
          Topic <span className="req">required</span>
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            maxLength={500}
            rows={3}
            required
            placeholder="e.g. Budget speech on fuel, jobs and digital India"
          />
        </label>
        <label>
          Speaker
          <input value={speaker} onChange={(e) => setSpeaker(e.target.value)} maxLength={200} />
        </label>
        <label>
          YouTube link
          <input
            value={youtube}
            onChange={(e) => setYoutube(e.target.value)}
            type="url"
            inputMode="url"
            placeholder="https://youtu.be/…"
          />
        </label>
        <label>
          Context links <span className="muted">up to 5, space separated</span>
          <input value={links} onChange={(e) => setLinks(e.target.value)} inputMode="url" />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="row">
          <button className="btn" disabled={busy || !topic.trim()}>
            {busy ? "Starting…" : "Generate brief"}
          </button>
          <button
            type="button"
            className="link"
            onClick={() => {
              setTopic(SAMPLE.topic);
              setSpeaker(SAMPLE.speaker);
            }}
          >
            Try a sample topic
          </button>
        </div>
      </form>
    </section>
  );
}
