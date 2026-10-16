import { useEffect, useRef, useState } from "react";
import { api, CLIP_MAX_BYTES, uploadClip, type Card, type ClaimView, type SessionView } from "../api";
import type { SignedIn } from "../auth";
import { CardTile } from "../components/CardTile";
import { captureTabAudio, openLive, youtubeId, type Capture, type LiveEvent } from "../live";
import { t } from "../i18n";

interface FeedItem {
  claim: ClaimView;
  prebunked: boolean;
  latency?: number;
}

type Mode = "idle" | "connecting" | "listening" | "ended";

export function Live({ id, user }: { id: string; user: SignedIn | null | undefined }) {
  const [session, setSession] = useState<SessionView | null>(null);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [cards, setCards] = useState<Record<string, Card>>({});
  const [heard, setHeard] = useState("");
  const [skip, setSkip] = useState("");
  const [mode, setMode] = useState<Mode>("idle");
  const [note, setNote] = useState("");
  const [line, setLine] = useState("");
  const ws = useRef<WebSocket | null>(null);
  const cap = useRef<Capture | null>(null);

  useEffect(() => {
    if (user) void api.session(id).then(setSession, () => setNote(t("live.loadFail")));
  }, [id, user]);

  useEffect(() => () => {
    cap.current?.stop();
    ws.current?.close();
  }, []);

  // Cards are immutable: fetch each once, as soon as an event names it.
  useEffect(() => {
    for (const f of feed) {
      const cid = f.claim.card_id;
      if (cid && !cards[cid]) void api.card(cid).then((c) => setCards((m) => ({ ...m, [cid]: c })), () => {});
    }
  }, [feed, cards]);

  const onEvent = (e: LiveEvent) => {
    if (e.type === "heard") {
      setHeard(e.text);
      setSkip("");
    } else if (e.type === "skipped") setSkip(t(`live.skip.${e.reason}`));
    else if (e.type === "error") setNote(e.code === "audio_unavailable" ? t("live.audioUnavailable") : t("live.wrong"));
    else if (e.type === "match" || e.type === "checking") {
      const claim: ClaimView = {
        id: e.claim_id, text: e.text, lang: "en", source: "live",
        status: e.type === "match" ? "proved" : "checking",
        card_id: e.type === "match" ? e.card_id : null,
        verdict: e.type === "match" ? e.verdict : null,
      };
      setFeed((f) => [{ claim, prebunked: e.type === "match", latency: e.type === "match" ? e.latency_ms : undefined }, ...f]);
    } else if (e.type === "proved" || e.type === "failed") {
      setFeed((f) => f.map((it) => it.claim.id !== e.claim_id ? it : {
        ...it,
        latency: e.type === "proved" ? e.latency_ms : undefined,
        claim: { ...it.claim, status: e.type, card_id: e.type === "proved" ? e.card_id : null, verdict: e.type === "proved" ? e.verdict : null },
      }));
    }
  };

  const connect = async (): Promise<WebSocket | null> => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) return ws.current;
    setMode("connecting");
    try {
      const sock = await openLive(id, onEvent);
      sock.onclose = (c) => {
        setMode("ended");
        if (c.code === 4401) setNote(t("live.owner"));
      };
      ws.current = sock;
      return sock;
    } catch {
      setMode("idle");
      setNote(t("live.unreachable"));
      return null;
    }
  };

  const listen = async () => {
    setNote("");
    const sock = await connect();
    if (!sock) return;
    try {
      cap.current = await captureTabAudio(sock, () => setMode("ended"));
      setMode("listening");
    } catch {
      setMode("idle");
      setNote(t("live.shareTab"));
    }
  };

  const stop = () => {
    cap.current?.stop();
    ws.current?.send(JSON.stringify({ type: "stop" }));
    setMode("ended");
  };

  const sendClip = async (ev: React.ChangeEvent<HTMLInputElement>) => {
    const file = ev.target.files?.[0];
    ev.target.value = "";
    if (!file) return;
    if (file.size > CLIP_MAX_BYTES) return setNote(t("live.clipBig"));
    setNote(t("live.clipWorking"));
    try {
      const r = await uploadClip(id, file);
      (r.events as LiveEvent[]).forEach(onEvent);
      setNote(t("live.clipDone", { n: r.sentences }));
    } catch (e) {
      setNote(e instanceof Error ? e.message : t("live.clipFail"));
    }
  };

  const sendLine = async (ev: React.FormEvent) => {
    ev.preventDefault();
    const text = line.trim();
    if (!text) return;
    const sock = await connect();
    if (!sock) return;
    if (mode !== "listening") setMode("listening");
    sock.send(JSON.stringify({ type: "text", text }));
    setLine("");
  };

  if (!session) return <section className="panel narrow center"><p className="muted">{note || t("live.loading")}</p></section>;
  const vid = session.youtube_url ? youtubeId(session.youtube_url) : null;
  const ready = session.claims.filter((c) => c.source === "predicted" && c.card_id).length;
  const hits = feed.filter((f) => f.prebunked);
  const fastest = hits.length ? Math.min(...hits.map((h) => h.latency ?? Infinity)) : null;

  return (
    <section className="live">
      <div className="brief-head">
        <div>
          <p className="eyebrow">{t("live.eyebrow", { n: ready })}</p>
          <h1>{session.topic}</h1>
        </div>
        <div className="live-stats" aria-live="polite">
          <span><b>{hits.length}</b> {t("live.instant")}</span>
          <span><b>{feed.length - hits.length}</b> {t("live.checkedLive")}</span>
          {fastest !== null && <span className="latency">{t("live.fastest", { ms: fastest })}</span>}
        </div>
      </div>

      <div className="live-grid">
        <div className="stage">
          {vid ? (
            <iframe
              className="player"
              src={`https://www.youtube-nocookie.com/embed/${vid}?rel=0&playsinline=1`}
              title={t("live.videoTitle")}
              allow="autoplay; encrypted-media; picture-in-picture"
              allowFullScreen
            />
          ) : (
            <div className="player empty"><p className="muted">{t("live.noVideo")}</p></div>
          )}
          <div className="controls">
            {mode === "listening" ? (
              <button className="btn ghost" onClick={stop}><span className="rec" aria-hidden="true" /> {t("live.stop")}</button>
            ) : (
              <button className="btn" disabled={mode === "connecting"} onClick={() => void listen()}>
                {mode === "connecting" ? t("live.connecting") : t("live.start")}
              </button>
            )}
            <p className="heard" aria-live="polite">{heard ? t("live.heard", { text: heard }) : t("live.privacy")}{skip && <span className="skip"> · {skip}</span>}</p>
          </div>
          <form className="line" onSubmit={(e) => void sendLine(e)}>
            <input
              value={line}
              onChange={(e) => setLine(e.target.value)}
              placeholder={t("live.linePh")}
              maxLength={600}
              aria-label={t("live.lineLabel")}
            />
            <button className="btn small" type="submit">{t("live.check")}</button>
          </form>
          <label className="clip">
            {t("live.clip")}
            <input type="file" accept="audio/*" onChange={(e) => void sendClip(e)} aria-label={t("live.clipLabel")} />
          </label>
          {note && <p className="note">{note}</p>}
        </div>

        <div className="feed">
          {feed.length === 0 && (
            <div className="tile pending feed-empty"><p className="muted">{t("live.empty")}</p></div>
          )}
          {feed.map((f) => (
            <div className="feed-item" key={f.claim.id}>
              <div className="feed-meta">
                <span className={`badge ${f.prebunked ? "b-pre" : "b-live"}`}>{f.prebunked ? "PREBUNKED" : "LIVE"}</span>
                {f.latency !== undefined && <span className="latency">{f.latency} ms</span>}
              </div>
              <CardTile claim={f.claim} card={f.claim.card_id ? cards[f.claim.card_id] : undefined} />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
