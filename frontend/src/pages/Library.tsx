import { useCallback, useEffect, useRef, useState, type CSSProperties, type MouseEvent } from "react";
import { ApiError, library, type LibraryCard, type LibraryPage, type Verdict } from "../api";
import { tgText } from "../components/CardTile";
import { VerdictPill } from "../components/VerdictPill";
import { getLang, t, type Key } from "../i18n";
import { navigate } from "../router";
import { VERDICT } from "../verdict";

// Proof Library (/cards, p75): every card we have issued, searchable and filterable.
// State lives in the URL (?q=&v=&t=) so a filtered view can be shared as a link.

export const WINDOWS = ["all", "24h", "7d", "30d"] as const;
export type Window = (typeof WINDOWS)[number];
const HOURS: Record<Window, number> = { all: 0, "24h": 24, "7d": 24 * 7, "30d": 24 * 30 };
const ORDER: Verdict[] = ["TRUE", "FALSE", "MISLEADING", "UNVERIFIABLE"];
const BOT = "https://t.me/ProofCardAgentBot";

/** Window start, floored to the hour so every visitor in that hour shares one CDN entry. */
export function sinceFor(w: Window, now = Date.now()): string | null {
  if (w === "all") return null;
  const hour = 3_600_000;
  return new Date(Math.floor((now - HOURS[w] * hour) / hour) * hour).toISOString();
}

export function readUrl(search: string): { q: string; verdicts: Verdict[]; win: Window } {
  const p = new URLSearchParams(search);
  const verdicts = (p.get("v") ?? "")
    .split(",")
    .filter((v): v is Verdict => (ORDER as string[]).includes(v));
  const w = p.get("t") as Window | null;
  return { q: (p.get("q") ?? "").slice(0, 200), verdicts, win: w && WINDOWS.includes(w) ? w : "all" };
}

export function writeUrl(q: string, verdicts: Verdict[], win: Window): string {
  const p = new URLSearchParams();
  if (q.trim()) p.set("q", q.trim());
  if (verdicts.length) p.set("v", verdicts.join(","));
  if (win !== "all") p.set("t", win);
  const qs = p.toString();
  return `/cards${qs ? `?${qs}` : ""}`;
}

/** Splits text around the query's words so matches can be marked. Case and script aware. */
export function highlight(text: string, q: string): { s: string; hit: boolean }[] {
  const words = q
    .split(/\s+/)
    .map((w) => w.trim())
    .filter((w) => w.length >= 2)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!words.length) return [{ s: text, hit: false }];
  const re = new RegExp(`(${words.join("|")})`, "giu");
  return text
    .split(re)
    .filter(Boolean)
    .map((s) => ({ s, hit: words.some((w) => new RegExp(`^${w}$`, "iu").test(s)) }));
}

function when(iso: string): string {
  const d = new Date(iso);
  const mins = Math.round((Date.now() - d.getTime()) / 60_000);
  const rtf = new Intl.RelativeTimeFormat(getLang() === "hi" ? "hi" : "en", { numeric: "auto" });
  if (mins < 60) return rtf.format(-Math.max(mins, 0), "minute");
  if (mins < 60 * 24) return rtf.format(-Math.round(mins / 60), "hour");
  if (mins < 60 * 24 * 7) return rtf.format(-Math.round(mins / 1440), "day");
  return d.toLocaleDateString(getLang() === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short", year: "numeric" });
}

/** Counts up to the total once (light: one rAF loop, skipped for reduced motion). */
function useCountUp(target: number): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches || target < 10) {
      setN(target);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / 900);
      setN(Math.round(target * (1 - Math.pow(1 - k, 3))));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return n;
}

/** WhatsApp / Telegram share links for one card; the message arrives already written. */
export function shareLinks(id: string, verdict: Verdict, claim: string, origin = location.origin) {
  const url = `${origin}/v/${id}`;
  const text = tgText(verdict, claim);
  return {
    url,
    text,
    whatsapp: `https://wa.me/?text=${encodeURIComponent(`${text}\n${url}`)}`,
    telegram: `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`,
  };
}

/** Share straight from the library: the phone's own share sheet, else a small menu. */
function ShareButton({ card }: { card: LibraryCard }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const links = shareLinks(card.id, card.verdict, card.claim);

  useEffect(() => {
    if (!open) return;
    const off = (e: Event) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    addEventListener("pointerdown", off);
    addEventListener("keydown", esc);
    return () => {
      removeEventListener("pointerdown", off);
      removeEventListener("keydown", esc);
    };
  }, [open]);

  const onShare = async (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (typeof navigator.share === "function" && matchMedia("(pointer: coarse)").matches) {
      try {
        await navigator.share({ title: "Proof Card", text: links.text, url: links.url });
      } catch {
        /* user closed the sheet */
      }
      return;
    }
    setOpen((o) => !o);
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(links.url);
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
        setOpen(false);
      }, 1200);
    } catch {
      setOpen(false);
    }
  };

  return (
    <span className="lib-share" ref={box}>
      <button type="button" className="share-btn" aria-haspopup="menu" aria-expanded={open} onClick={onShare}>
        <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
          <path d="M12 3v12M7 8l5-5 5 5M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span>{t("lib.share")}</span>
      </button>
      {open && (
        <span className="share-menu" role="menu">
          <a role="menuitem" href={links.whatsapp} target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)}>
            WhatsApp
          </a>
          <a role="menuitem" href={links.telegram} target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)}>
            Telegram
          </a>
          <button type="button" role="menuitem" onClick={copy}>
            {copied ? t("lib.copied") : t("tile.copy")}
          </button>
        </span>
      )}
    </span>
  );
}

function LibTile({ card, q, i }: { card: LibraryCard; q: string; i: number }) {
  return (
    <article className="lib-tile" style={{ "--i": Math.min(i % 24, 12) } as CSSProperties}>
      <div className="tile-top">
        <VerdictPill verdict={card.verdict} />
        <time className="tile-meta" dateTime={card.created_at}>
          {when(card.created_at)}
        </time>
      </div>
      <p className="lib-claim">
        <a className="lib-link" href={`/v/${card.id}`}>
          “
          {highlight(card.claim, q).map((p, n) => (p.hit ? <mark key={n}>{p.s}</mark> : <span key={n}>{p.s}</span>))}
          ”
        </a>
      </p>
      {card.excerpt && <p className="lib-why">{card.excerpt}</p>}
      <div className="lib-foot">
        <ShareButton card={card} />
        <span className="lib-open" aria-hidden="true">
          {t("lib.open")} →
        </span>
      </div>
    </article>
  );
}

export function Library() {
  const init = readUrl(location.search);
  const [q, setQ] = useState(init.q);
  const [typed, setTyped] = useState(init.q);
  const [verdicts, setVerdicts] = useState<Verdict[]>(init.verdicts);
  const [win, setWin] = useState<Window>(init.win);
  const [page, setPage] = useState<LibraryPage | null>(null);
  const [items, setItems] = useState<LibraryCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  const total = useCountUp(page?.total ?? 0);

  // Debounce typing: one request per pause, not per key.
  useEffect(() => {
    const id = window.setTimeout(() => setQ(typed), 250);
    return () => window.clearTimeout(id);
  }, [typed]);

  useEffect(() => {
    history.replaceState(null, "", writeUrl(q, verdicts, win));
    const ctl = new AbortController();
    setLoading(true);
    setError(null);
    library({ q, verdicts, since: sinceFor(win) }, null, ctl.signal)
      .then((p) => {
        setPage(p);
        setItems(p.items);
      })
      .catch((e: unknown) => {
        if (!ctl.signal.aborted) setError(e instanceof ApiError ? e.message : t("lib.error"));
      })
      .finally(() => {
        if (!ctl.signal.aborted) setLoading(false);
      });
    return () => ctl.abort();
  }, [q, verdicts, win]);

  const loadMore = useCallback(() => {
    if (!page?.next_cursor || more) return;
    setMore(true);
    library({ q, verdicts, since: sinceFor(win) }, page.next_cursor)
      .then((p) => {
        setPage((old) => ({ ...p, counts: old?.counts ?? p.counts }));
        setItems((have) => {
          const seen = new Set(have.map((c) => c.id));
          return [...have, ...p.items.filter((c) => !seen.has(c.id))];
        });
      })
      .catch(() => setError(t("lib.error")))
      .finally(() => setMore(false));
  }, [page, more, q, verdicts, win]);

  // Infinite scroll, with the button below as the keyboard / no-IO fallback.
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver((e) => e[0]?.isIntersecting && loadMore(), { rootMargin: "600px" });
    io.observe(el);
    return () => io.disconnect();
  }, [loadMore]);

  const toggle = (v: Verdict) => setVerdicts((have) => (have.includes(v) ? have.filter((x) => x !== v) : [...have, v]));
  const counts = page?.counts;
  const all = counts ? ORDER.reduce((n, v) => n + counts[v], 0) : 0;

  return (
    <div className="lib">
      <section className="lib-hero">
        <div>
          <p className="eyebrow">{t("lib.eyebrow")}</p>
          <h1 className="serif lib-h1">{t("lib.h1")}</h1>
          <p className="lib-sub muted">{t("lib.sub")}</p>
        </div>
        <div className="lib-stat" aria-live="polite">
          <span className="lib-num">{page ? total.toLocaleString(getLang() === "hi" ? "hi-IN" : "en-IN") : "·"}</span>
          <span className="lib-num-l">{t("lib.total")}</span>
          <div className="lib-ctas">
            <button className="btn small" onClick={() => navigate("/new")}>
              {t("lib.verifyNew")}
            </button>
            <a className="btn small ghost" href={BOT} target="_blank" rel="noopener noreferrer">
              {t("lib.askBot")}
            </a>
          </div>
        </div>
      </section>

      <div className="lib-bar" role="search">
        <label className="lib-search">
          <span className="sr-only">{t("lib.searchLabel")}</span>
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            type="search"
            value={typed}
            maxLength={200}
            placeholder={t("lib.searchPh")}
            onChange={(e) => setTyped(e.target.value)}
            enterKeyHint="search"
          />
          {typed && (
            <button className="lib-clear" aria-label={t("lib.clear")} onClick={() => setTyped("")}>
              ×
            </button>
          )}
        </label>
        <div className="lib-filters">
          <div className="lib-chips" role="group" aria-label={t("lib.verdictLabel")}>
            <button className={`lib-chip${verdicts.length ? "" : " on"}`} aria-pressed={!verdicts.length} onClick={() => setVerdicts([])}>
              {t("lib.all")} {counts && <b>{all}</b>}
            </button>
            {ORDER.map((v) => (
              <button
                key={v}
                className={`lib-chip ${VERDICT[v].cls}-chip${verdicts.includes(v) ? " on" : ""}`}
                aria-pressed={verdicts.includes(v)}
                onClick={() => toggle(v)}
              >
                <span aria-hidden="true">{VERDICT[v].icon}</span> {t(`verdict.${v}`)} {counts && <b>{counts[v]}</b>}
              </button>
            ))}
          </div>
          <div className="lib-seg" role="group" aria-label={t("lib.timeLabel")}>
            {WINDOWS.map((w) => (
              <button key={w} className={win === w ? "on" : ""} aria-pressed={win === w} onClick={() => setWin(w)}>
                {t(`lib.t.${w}` as Key)}
              </button>
            ))}
          </div>
        </div>
      </div>

      <p className="lib-meta muted" role="status">
        {loading ? t("lib.loading") : page && (q.trim() ? t("lib.results", { n: page.matched, q: q.trim() }) : t("lib.count", { n: page.matched }))}
      </p>

      {error && <p className="note banner">{error}</p>}

      {loading && !items.length ? (
        <div className="lib-grid" aria-hidden="true">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="lib-tile skeleton" />
          ))}
        </div>
      ) : items.length ? (
        <div className={`lib-grid${loading ? " dim" : ""}`}>
          {items.map((c, i) => (
            <LibTile key={c.id} card={c} q={q} i={i} />
          ))}
        </div>
      ) : (
        !error && (
          <div className="lib-empty">
            <p className="serif">{t("lib.emptyH")}</p>
            <p className="muted">{t("lib.emptyBody")}</p>
            <button className="btn" onClick={() => navigate("/new")}>
              {t("lib.verifyNew")}
            </button>
          </div>
        )
      )}

      <div ref={sentinel} />
      {page?.next_cursor && (
        <div className="lib-more">
          <button className="btn ghost" disabled={more} onClick={loadMore}>
            {more ? t("lib.loading") : t("lib.more")}
          </button>
        </div>
      )}
    </div>
  );
}
