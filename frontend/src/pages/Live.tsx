import { useEffect, useRef, useState } from "react";
import { api, type Card, type ClaimView, type SessionView } from "../api";
import type { SignedIn } from "../auth";
import { CardTile } from "../components/CardTile";
import { captureTabAudio, openLive, youtubeId, type Capture, type LiveEvent } from "../live";

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
  const [mode, setMode] = useState<Mode>("idle");
  const [note, setNote] = useState("");
  const [line, setLine] = useState("");
  const ws = useRef<WebSocket | null>(null);
  const cap = useRef<Capture | null>(null);

  useEffect(() => {
    if (user) void api.session(id).then(setSession, () => setNote("Couldn't load this brief."));
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
    if (e.type === "heard") setHeard(e.text);
    else if (e.type === "error") setNote(e.code === "audio_unavailable" ? "Live audio needs the cloud model. Type the line below instead." : "Something went wrong.");
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
        if (c.code === 4401) setNote("Sign in as the owner of this brief to go live.");
      };
      ws.current = sock;
      return sock;
    } catch {
      setMode("idle");
      setNote("Couldn't reach the live service.");
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
      setNote("Pick this tab and tick “Share tab audio” to listen.");
    }
  };

  const stop = () => {
    cap.current?.stop();
    ws.current?.send(JSON.stringify({ type: "stop" }));
    setMode("ended");
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

  if (!session) return <section className="panel narrow center"><p className="muted">{note || "Loading…"}</p></section>;
  const vid = session.youtube_url ? youtubeId(session.youtube_url) : null;
  const ready = session.claims.filter((c) => c.source === "predicted" && c.card_id).length;
  const hits = feed.filter((f) => f.prebunked);
  const fastest = hits.length ? Math.min(...hits.map((h) => h.latency ?? Infinity)) : null;

  return (
    <section className="live">
      <div className="brief-head">
        <div>
          <p className="eyebrow">Live · {ready} claims prebunked</p>
          <h1>{session.topic}</h1>
        </div>
        <div className="live-stats" aria-live="polite">
          <span><b>{hits.length}</b> instant</span>
          <span><b>{feed.length - hits.length}</b> checked live</span>
          {fastest !== null && <span className="latency">fastest {fastest} ms</span>}
        </div>
      </div>

      <div className="live-grid">
        <div className="stage">
          {vid ? (
            <iframe
              className="player"
              src={`https://www.youtube-nocookie.com/embed/${vid}?rel=0&playsinline=1`}
              title="Video being fact checked"
              allow="autoplay; encrypted-media; picture-in-picture"
              allowFullScreen
            />
          ) : (
            <div className="player empty"><p className="muted">No video on this brief. Play the stream in this tab, then listen.</p></div>
          )}
          <div className="controls">
            {mode === "listening" ? (
              <button className="btn ghost" onClick={stop}><span className="rec" aria-hidden="true" /> Stop listening</button>
            ) : (
              <button className="btn" disabled={mode === "connecting"} onClick={() => void listen()}>
                {mode === "connecting" ? "Connecting…" : "Start listening"}
              </button>
            )}
            <p className="heard" aria-live="polite">{heard ? `Heard: “${heard}”` : "We listen to this tab only. Nothing is recorded."}</p>
          </div>
          <form className="line" onSubmit={(e) => void sendLine(e)}>
            <input
              value={line}
              onChange={(e) => setLine(e.target.value)}
              placeholder="Or type a line the speaker said"
              maxLength={600}
              aria-label="Line the speaker said"
            />
            <button className="btn small" type="submit">Check</button>
          </form>
          {note && <p className="note">{note}</p>}
        </div>

        <div className="feed">
          {feed.length === 0 && (
            <div className="tile pending feed-empty"><p className="muted">Claims appear here the moment they're said. Prebunked ones arrive instantly.</p></div>
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
