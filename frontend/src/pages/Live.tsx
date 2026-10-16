import { useEffect, useRef, useState } from "react";
import { onePerCard } from "../verdict";
import { api, CLIP_MAX_BYTES, uploadClip, watchUrl, type Card, type ClaimView, type SessionView } from "../api";
import type { SignedIn } from "../auth";
import { CardTile } from "../components/CardTile";
import {
  captureTabAudio,
  clock,
  connectLive,
  loadYouTube,
  openLive,
  replayDue,
  youtubeId,
  type Capture,
  type LiveEvent,
  type LiveLink,
  type YtPlayer,
} from "../live";
import { t } from "../i18n";
import { isSampleVideo, SAMPLE_CLIP } from "../sample";

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
  const [replay, setReplay] = useState(false);
  const [now, setNow] = useState(0);
  const playerEl = useRef<HTMLDivElement | null>(null);
  const ws = useRef<LiveLink | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const cap = useRef<Capture | null>(null);

  useEffect(() => {
    if (user) void api.session(id).then(setSession, () => setNote(t("live.loadFail")));
  }, [id, user]);

  useEffect(() => () => {
    cap.current?.stop();
    ws.current?.close();
  }, []);

  const replayVid = session?.youtube_url ? youtubeId(session.youtube_url) : null;
  useEffect(() => {
    if (!replay || !replayVid || !playerEl.current) return;
    let player: YtPlayer | null = null;
    let alive = true;
    const el = playerEl.current;
    void loadYouTube().then((YT) => {
      if (!alive) return;
      // The API replaces its target node: give it one React doesn't own.
      const target = document.createElement("div");
      el.replaceChildren(target);
      player = new YT.Player(target, {
        videoId: replayVid,
        width: "100%",
        height: "100%",
        playerVars: { rel: 0, playsinline: 1 },
      });
    }, () => setNote(t("live.wrong")));
    const tick = window.setInterval(() => {
      const s = player?.getCurrentTime?.();
      if (typeof s === "number") setNow(s);
    }, 250);
    return () => {
      alive = false;
      window.clearInterval(tick);
      player?.destroy();
      el.replaceChildren();
    };
  }, [replay, replayVid]);

  const shown: FeedItem[] =
    replay && session
      ? replayDue(session.claims, now).map((c) => ({ claim: c, prebunked: Boolean(c.matched_claim_id) }))
      : feed;

  // Cards are immutable: fetch each once, as soon as an event names it.
  useEffect(() => {
    for (const f of shown) {
      const cid = f.claim.card_id;
      if (cid && !cards[cid]) void api.card(cid).then((c) => setCards((m) => ({ ...m, [cid]: c })), () => {});
    }
  }, [shown, cards]);

  const feedRef = useRef(feed);
  feedRef.current = feed;
  const feedHasCard = (card: string, except: string) =>
    feedRef.current.some((it) => it.claim.card_id === card && it.claim.id !== except);

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
      // one tile per card: a second wording of a claim already on screen adds nothing
      setFeed((f) => e.type === "match" && f.some((it) => it.claim.card_id === e.card_id) ? f
        : [{ claim, prebunked: e.type === "match", latency: e.type === "match" ? e.latency_ms : undefined }, ...f]);
    } else if (e.type === "proved" && e.card_id && feedHasCard(e.card_id, e.claim_id)) {
      setFeed((f) => f.filter((it) => it.claim.id !== e.claim_id));
    } else if (e.type === "proved" || e.type === "failed") {
      setFeed((f) => f.map((it) => it.claim.id !== e.claim_id ? it : {
        ...it,
        latency: e.type === "proved" ? e.latency_ms : undefined,
        claim: { ...it.claim, status: e.type, card_id: e.type === "proved" ? e.card_id : null, verdict: e.type === "proved" ? e.verdict : null },
      }));
    }
  };

  // After a drop: cards made while we were away are stored, so reload the session and fold
  // its heard claims into the feed (keyed by id, nothing shown twice).
  const resume = () => {
    void api.session(id).then((s) => {
      setSession(s);
      setFeed((f) => {
        const byId = new Map(f.map((it) => [it.claim.id, it]));
        for (const c of s.claims.filter((x) => x.source === "live")) {
          const had = byId.get(c.id);
          byId.set(c.id, { claim: c, prebunked: c.matched ?? had?.prebunked ?? false, latency: had?.latency });
        }
        return onePerCard([...byId.values()], (it) => it.claim.card_id);
      });
    }, () => {});
  };

  const connect = async (): Promise<LiveLink | null> => {
    if (ws.current) return ws.current;
    setMode("connecting");
    try {
      const sock = await connectLive((ev) => openLive(id, ev), {
        onEvent,
        onReopen: resume,
        onState: (st, code) => {
          setReconnecting(st === "reconnecting");
          if (st !== "closed") return;
          ws.current = null;
          setMode("ended");
          setNote(code === 4401 ? t("live.owner") : code === 1000 ? "" : t("live.lost"));
        },
      });
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
    ws.current?.close();
    ws.current = null;
    setMode("ended");
  };

  const [copied, setCopied] = useState(false);
  const toggleShare = async () => {
    if (!session) return;
    try {
      const r = await api.share(id, !session.public_view);
      setSession({ ...session, public_view: r.public_view });
      if (r.public_view) {
        await navigator.clipboard?.writeText(watchUrl(id)).then(() => setCopied(true), () => {});
      }
    } catch {
      setNote(t("live.wrong"));
    }
  };

  const sendClip = async (ev: React.ChangeEvent<HTMLInputElement>) => {
    const file = ev.target.files?.[0];
    ev.target.value = "";
    if (file) await checkClip(file);
  };

  // The Trump sample's own audio, served with the site: no file hunting for a judge.
  const sampleClip = async () => {
    setNote(t("live.clipWorking"));
    try {
      const r = await fetch(SAMPLE_CLIP);
      if (!r.ok) throw new Error(t("live.clipFail"));
      await checkClip(new File([await r.blob()], "trump-nobel.mp3", { type: "audio/mpeg" }));
    } catch (e) {
      setNote(e instanceof Error ? e.message : t("live.clipFail"));
    }
  };

  const checkClip = async (file: File) => {
    if (file.size > CLIP_MAX_BYTES) return setNote(t("live.clipBig"));
    setNote(t("live.clipWorking"));
    try {
      const timed = Boolean(session?.youtube_url);
      const r = await uploadClip(id, file, timed, (done, total) =>
        setNote(total == null ? t("live.clipWorking") : t("live.clipProgress", { done, total })),
      );
      (r.events as LiveEvent[]).forEach(onEvent);
      if (timed) void api.session(id).then(setSession, () => {});
      setNote(t("live.clipDone", { n: r.sentences }));
    } catch (e) {
      setNote(e instanceof Error ? e.message : t("live.clipFail"));
    }
  };

  const telegram = async () => {
    // Open the tab synchronously (popup blockers), then point it at the deep link.
    const tab = window.open("", "_blank");
    try {
      const { url } = await api.telegramLink(id);
      if (tab) tab.location.href = url;
      else window.location.href = url;
      setNote(t("live.tgOpen"));
    } catch (e) {
      tab?.close();
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
  const hits = shown.filter((f) => f.prebunked);
  const canReplay = Boolean(vid) && session.claims.some((c) => c.source === "live" && c.t_offset_s != null);
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
          <span><b>{shown.length - hits.length}</b> {t("live.checkedLive")}</span>
          {fastest !== null && <span className="latency">{t("live.fastest", { ms: fastest })}</span>}
        </div>
      </div>

      <div className="live-grid">
        <div className="stage">
          {replay && vid ? (
            <div className="player" ref={playerEl} />
          ) : vid ? (
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
          {canReplay && (
            <button className="btn ghost small" type="button" onClick={() => setReplay((r) => !r)}>
              {replay ? t("live.replayOff") : t("live.replay")}
            </button>
          )}
          {replay && <p className="note">{t("live.replayNote")} · {clock(now)}</p>}
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
          {isSampleVideo(vid) && (
            <div className="sample-clip">
              <button className="btn" type="button" onClick={() => void sampleClip()}>
                {t("live.sampleClip")}
              </button>
              <p className="muted small">{t("live.sampleHint")}</p>
            </div>
          )}
          <label className="clip">
            {t("live.clip")}
            <input type="file" accept="audio/*" onChange={(e) => void sendClip(e)} aria-label={t("live.clipLabel")} />
          </label>
          <button className="btn ghost small" type="button" onClick={() => void telegram()}>
            {t("live.tg")}
          </button>
          <div className="share-view">
            <button className="btn small ghost" aria-pressed={session.public_view} onClick={() => void toggleShare()}>
              {session.public_view ? t("live.shareOff") : t("live.shareOn")}
            </button>
            {session.public_view && (
              <a className="link" href={watchUrl(id)} target="_blank" rel="noopener">
                {copied ? t("live.shareCopied") : watchUrl(id)}
              </a>
            )}
          </div>
          {reconnecting && <p className="note banner" role="status">{t("live.reconnecting")}</p>}
          {note && <p className="note">{note}</p>}
        </div>

        <div className="feed">
          {shown.length === 0 && (
            <div className="tile pending feed-empty"><p className="muted">{t("live.empty")}</p></div>
          )}
          {shown.map((f) => (
            <div className="feed-item" key={f.claim.id}>
              <div className="feed-meta">
                <span className={`badge ${f.prebunked ? "b-pre" : "b-live"}`}>{f.prebunked ? "PREBUNKED" : "LIVE"}</span>
                {replay && f.claim.t_offset_s != null && <span className="latency">{clock(f.claim.t_offset_s)}</span>}
                {f.latency !== undefined && <span className="latency">{f.latency} ms</span>}
              </div>
              <CardTile claim={f.claim} card={f.claim.card_id ? cards[f.claim.card_id] : undefined} showSource={false} />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
