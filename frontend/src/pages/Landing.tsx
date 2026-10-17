import { useEffect, useRef, useState, type ReactNode } from "react";
import type { SignedIn } from "../auth";
import { VerdictPill } from "../components/VerdictPill";
import { navigate } from "../router";
import { t, type Key } from "../i18n";

export const BOT = "ProofCardAgentBot";

// Illustrative scenes: design samples, not checked facts (labelled on screen).
const SCENES = [
  { v: "FALSE", src: "land.src1", claim: "land.s1.claim", why: "land.s1.why", host: "tracker.gov.in" },
  { v: "TRUE", src: "land.src2", claim: "land.s2.claim", why: "land.s2.why", host: "legislative.gov.in" },
  { v: "MISLEADING", src: "land.src3", claim: "land.s3.claim", why: "land.s3.why", host: "ppac.gov.in" },
] as const;
const SOURCES = ["MoSPI", "RBI", "World Bank", "BLS", "Eurostat", "GST portal", "IMF", "Constitution of India"];

/** Short stable hex for the illustrative fingerprints (not a real hash of anything). */
export function demoHash(s: string): string {
  let h = 2166136261;
  for (const ch of s) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0;
  return (h.toString(16).padStart(8, "0") + ((h * 2654435761) >>> 0).toString(16).padStart(8, "0")).slice(0, 16);
}

function reducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Adds .in once the element scrolls into view (CSS does the motion). */
function useInView<T extends HTMLElement>(threshold = 0.18) {
  const ref = useRef<T | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      el.classList.add("in");
      return;
    }
    const io = new IntersectionObserver(
      (es) => {
        for (const e of es) {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        }
      },
      { threshold, rootMargin: "0px 0px -8% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);
  return ref;
}

export function Reveal({ children, delay = 0, className = "" }: { children: ReactNode; delay?: number; className?: string }) {
  const ref = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className={`reveal ${className}`.trim()} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

/** Hero: a claim arrives, official sources are read, the passage decides, the verdict is stamped. */
function LiveProof() {
  const [i, setI] = useState(0);
  const [phase, setPhase] = useState(reducedMotion() ? 3 : 0);
  const [typed, setTyped] = useState(reducedMotion() ? 999 : 0);
  const s = SCENES[i % SCENES.length] ?? SCENES[0];
  const claim = t(s.claim);
  useEffect(() => {
    if (reducedMotion()) return;
    if (phase === 0) {
      if (typed < claim.length) {
        const id = setTimeout(() => setTyped((n) => n + 2), 28);
        return () => clearTimeout(id);
      }
      const id = setTimeout(() => setPhase(1), 350);
      return () => clearTimeout(id);
    }
    const wait = phase === 1 ? 1500 : phase === 2 ? 1300 : 2800;
    const id = setTimeout(() => {
      if (phase < 3) setPhase(phase + 1);
      else {
        setI((i + 1) % SCENES.length);
        setTyped(0);
        setPhase(0);
      }
    }, wait);
    return () => clearTimeout(id);
  }, [phase, typed, claim.length, i]);
  return (
    <div className="live" aria-label={t("land.samples")}>
      <div className="live-top">
        <span className="live-dot" aria-hidden="true" />
        {t("land.liveLabel")}
        <span className="live-ill">{t("land.illustrative")}</span>
      </div>
      <p className="live-src">{t(s.src)}</p>
      <p className="live-claim">
        {claim.slice(0, typed)}
        {phase === 0 && <span className="caret" aria-hidden="true" />}
      </p>
      <div className={`live-step ${phase >= 1 ? "on" : ""}`}>
        <span className="mono">{phase === 1 ? t("land.checking") : s.host}</span>
        <span className={`bar ${phase === 1 ? "run" : phase > 1 ? "full" : ""}`} />
      </div>
      <div className={`live-step passage ${phase >= 2 ? "on" : ""}`}>
        <span className="mono label">{t("land.passage")}</span>
        <mark>{t(s.why)}</mark>
      </div>
      <div className={`live-verdict ${phase >= 3 ? "on" : ""}`}>
        <span className="stamp">
          <VerdictPill verdict={s.v} />
        </span>
        <span className="mono fp">
          {t("land.fingerprint")} {demoHash(claim + s.v)}
        </span>
      </div>
    </div>
  );
}

/** Decorative QR-style mark (three finder squares + seeded modules); the real QR is on the card PNG. */
export function Qr({ seed }: { seed: string }) {
  const N = 21;
  const hex = Array.from({ length: 8 }, (_, k) => demoHash(seed + k)).join("");
  const finder = (x: number, y: number) => x >= 0 && x < 7 && y >= 0 && y < 7;
  const cells: [number, number][] = [];
  for (let y = 0; y < N; y++)
    for (let x = 0; x < N; x++) {
      if (finder(x, y) || finder(x - 14, y) || finder(x, y - 14)) continue;
      if (parseInt(hex[(y * N + x) % hex.length] ?? "0", 16) % 2) cells.push([x, y]);
    }
  const box = (x: number, y: number) => (
    <g key={`${x}-${y}`}>
      <rect x={x + 0.5} y={y + 0.5} width={6} height={6} fill="none" stroke="currentColor" />
      <rect x={x + 2} y={y + 2} width={3} height={3} fill="currentColor" />
    </g>
  );
  return (
    <svg className="qr" viewBox="0 0 21 21" aria-hidden="true" shapeRendering="crispEdges">
      {box(0, 0)}
      {box(14, 0)}
      {box(0, 14)}
      {cells.map(([x, y]) => (
        <rect key={`${x}.${y}`} x={x} y={y} width={1} height={1} fill="currentColor" />
      ))}
    </svg>
  );
}

function StepVisual({ n }: { n: number }) {
  if (n === 0)
    return (
      <div className="vis">
        <div className="vis-url mono">youtube.com/watch?v=…</div>
        <p className="vis-cap">{t("land.vis.predicted")}</p>
        {SCENES.map((s, k) => (
          <div key={s.v} className="vis-row" style={{ animationDelay: `${k * 160}ms` }}>
            <span className="vis-check">✓</span> {t(s.claim)}
          </div>
        ))}
      </div>
    );
  if (n === 1)
    return (
      <div className="vis">
        <div className="vis-line dim">… {t("land.vis.l1")}</div>
        <div className="vis-line hot">
          {t("land.s3.claim")}
          <VerdictPill verdict="MISLEADING" />
        </div>
        <div className="vis-line dim">{t("land.vis.l2")} …</div>
      </div>
    );
  if (n === 2)
    return (
      <div className="vis receipt">
        <VerdictPill verdict="FALSE" />
        <p className="vis-claim">{t("land.s1.claim")}</p>
        <Qr seed="card" />
        <p className="mono fp">
          {t("land.fingerprint")} {demoHash("card")}
        </p>
      </div>
    );
  return (
    <div className="vis tg">
      <div className="bubble me">
        <span className="mono small">{t("land.vis.forward")}</span>
        {t("land.s1.claim")}
      </div>
      <div className="bubble bot">
        <VerdictPill verdict="FALSE" />
        <span>{t("land.s1.why")}</span>
        <span className="tg-btn">{t("land.vis.open")}</span>
      </div>
    </div>
  );
}

const STEPS: readonly [string, Key, Key][] = [
  ["01", "land.before", "land.beforeBody"],
  ["02", "land.during", "land.duringBody"],
  ["03", "land.after", "land.afterBody"],
  ["04", "land.anyone", "land.anyoneBody"],
];

/** How it works: the visual stays pinned while the four steps scroll past it. */
function StickySteps() {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLDivElement | null)[]>([]);
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (es) => {
        for (const e of es) if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.n));
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);
  return (
    <section id="how" className="how">
      <div className="how-pin" aria-hidden="true">
        <div className="how-frame">
          {STEPS.map((_, k) => (
            <div key={k} className={`how-vis ${k === active ? "on" : ""}`}>
              <StepVisual n={k} />
            </div>
          ))}
        </div>
      </div>
      <div className="how-steps">
        {STEPS.map(([n, h, b], k) => (
          <div
            key={n}
            data-n={k}
            ref={(el) => {
              refs.current[k] = el;
            }}
            className={`how-step ${k === active ? "on" : ""}`}
          >
            <span className="step-n mono">{n}</span>
            <h3>{t(h)}</h3>
            <p>{t(b)}</p>
            <div className="how-inline">
              <StepVisual n={k} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/** A forwarded card gets its verdict edited; the fingerprint catches it. */
function Tamper() {
  const ref = useInView<HTMLDivElement>(0.45);
  const claim = t("land.s1.claim");
  return (
    <section className="tamper">
      <div className="tamper-copy">
        <p className="eyebrow">{t("land.tamperEyebrow")}</p>
        <h2 className="big serif">{t("land.tamperH")}</h2>
        <p className="lede">{t("land.tamperBody")}</p>
      </div>
      <div ref={ref} className="tamper-card receipt">
        <span className="tamper-v">
          <span className="was">
            <VerdictPill verdict="FALSE" />
          </span>
          <span className="now">
            <VerdictPill verdict="TRUE" />
          </span>
        </span>
        <p className="vis-claim">{claim}</p>
        <p className="mono fp ok">
          {t("land.fingerprint")} {demoHash(claim)}
        </p>
        <p className="mono fp bad">
          {t("land.mismatch")} · {t("land.changed")}
        </p>
        <span className="altered">{t("land.altered")}</span>
      </div>
    </section>
  );
}

const VS: readonly [Key, Key][] = [
  ["land.vs1h", "land.vs1"],
  ["land.vs2h", "land.vs2"],
  ["land.vs3h", "land.vs3"],
  ["land.vs4h", "land.vs4"],
  ["land.vs5h", "land.vs5"],
];

/** Section scroll progress (0..1) as --vs-p, a stage phase, and which points the scroll has reached. */
function useVsScroll(n: number) {
  const sec = useRef<HTMLElement | null>(null);
  const stage = useRef<HTMLDivElement | null>(null);
  const rows = useRef<(HTMLLIElement | null)[]>([]);
  useEffect(() => {
    const el = sec.current;
    if (!el) return;
    const paint = (p: number, lit: number, phase: number) => {
      el.style.setProperty("--vs-p", p.toFixed(3));
      if (stage.current) stage.current.dataset.phase = String(phase);
      rows.current.forEach((r, k) => r?.classList.toggle("on", k < lit));
    };
    if (reducedMotion() || typeof IntersectionObserver === "undefined") {
      paint(1, n, 2);
      return;
    }
    let raf = 0;
    const tick = () => {
      raf = 0;
      const vh = window.innerHeight || 800;
      const line = vh * 0.62;
      // The rail fills exactly as far as the reading line has reached down the list, so it meets each dot.
      const list = rows.current[0]?.parentElement?.getBoundingClientRect();
      const p = list ? Math.min(1, Math.max(0, (line - list.top) / Math.max(1, list.height))) : 0;
      let lit = 0;
      rows.current.forEach((row) => {
        if (row && row.getBoundingClientRect().top + 36 < line) lit++;
      });
      // The answer turns into proof only while the stage is on screen: by its own height on the page
      // (phones, one column) or by how many points are lit (desktop, where the copy column stays put).
      const st = stage.current?.getBoundingClientRect();
      const seen = !!st && st.top < vh * 0.8 && st.bottom > 0;
      const phase = !seen ? (lit >= n ? 2 : 0) : lit >= 4 || st.top < vh * 0.3 ? 2 : lit >= 2 || st.top < vh * 0.55 ? 1 : 0;
      paint(p, lit, phase);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(tick);
    };
    const io = new IntersectionObserver(
      ([e]) => {
        if (e?.isIntersecting) {
          window.addEventListener("scroll", onScroll, { passive: true });
          window.addEventListener("resize", onScroll);
          onScroll();
        } else {
          window.removeEventListener("scroll", onScroll);
          window.removeEventListener("resize", onScroll);
        }
      },
      { threshold: 0 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [n]);
  return { sec, stage, rows };
}

/** "Why not just ask an AI?": as you scroll, a plain answer turns into a proof card and each point lights up. */
function WhyNotAi() {
  const { sec, stage, rows } = useVsScroll(VS.length);
  const claim = t("land.s2.claim");
  return (
    <section id="why-ai" className="vs" aria-labelledby="vs-h" ref={sec}>
      <Reveal className="vs-copy">
        <p className="eyebrow">{t("land.vsEyebrow")}</p>
        <h2 id="vs-h" className="big serif">
          {t("land.vsH")}
        </h2>
        <p className="lede">{t("land.vsBody")}</p>
        <div className="vs-stage" ref={stage} data-phase="0" aria-hidden="true">
          <p className="vs-claim">{claim}</p>
          <div className="vs-ans">
            <span className="mono label">{t("land.vsAnsLabel")}</span>
            <p>{t("land.vsAns")}</p>
          </div>
          <div className="vs-proof">
            <span className="mono label">
              {t("land.passage")} · legislative.gov.in
            </span>
            <mark>{t("land.s2.why")}</mark>
            <div className="vs-verdict">
              <span className="stamp">
                <VerdictPill verdict="TRUE" />
              </span>
              <span className="mono fp">
                {t("land.fingerprint")} {demoHash(claim + "TRUE")}
              </span>
            </div>
          </div>
          <span className="live-ill">{t("land.illustrative")}</span>
        </div>
      </Reveal>
      <ol className="vs-list">
        {VS.map(([h, b], i) => (
          <li
            key={h}
            ref={(r) => {
              rows.current[i] = r;
            }}
          >
            <Reveal delay={i * 110} className="vs-row">
              <span className="vs-tick" aria-hidden="true">
                ✓
              </span>
              <div>
                <h3>{t(h)}</h3>
                <p>{t(b)}</p>
              </div>
            </Reveal>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function Landing(_props: { user: SignedIn | null | undefined }) {
  // /new offers Google or guest; never a direct Google popup from here.
  const start = () => navigate("/new");
  const bot = (
    <a className="btn ghost" href={`https://t.me/${BOT}?start=try`} target="_blank" rel="noreferrer">
      {t("land.bot")}
    </a>
  );
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">{t("land.eyebrow")}</p>
          <h1 className="serif">
            {t("land.h1a")}
            <em>{t("land.h1b")}</em>
            {t("land.h1c")}
          </h1>
          <p className="lede">{t("land.lede")}</p>
          <div className="row">
            <button className="btn" onClick={start}>
              {t("land.create")}
            </button>
            {bot}
            <a
              className="btn ghost"
              href="/how"
              onClick={(e) => {
                e.preventDefault();
                navigate("/how");
              }}
            >
              {t("land.howBtn")}
            </a>
          </div>
        </div>
        <LiveProof />
      </section>

      <div className="marquee" aria-label={t("land.sourcesH")}>
        <div className="marquee-track">
          {[...SOURCES, ...SOURCES].map((s, k) => (
            <span key={k}>{s}</span>
          ))}
        </div>
      </div>

      <section className="need" aria-labelledby="need-h">
        <Reveal>
          <p className="eyebrow">{t("land.needEyebrow")}</p>
          <h2 id="need-h" className="big serif">
            {t("land.needH")}
          </h2>
        </Reveal>
        <ol className="need-list">
          {(["land.need1", "land.need2", "land.need3"] as const).map((k, i) => (
            <li key={k}>
              <Reveal delay={i * 120}>{t(k)}</Reveal>
            </li>
          ))}
        </ol>
      </section>

      <StickySteps />

      <Tamper />

      <WhyNotAi />

      <Reveal className="trust">
        <h2 className="serif">{t("land.trustH")}</h2>
        <p>
          {t("land.trust1")}
          <strong>{t("verdict.UNVERIFIABLE")}</strong>
          {t("land.trust2")}
        </p>
      </Reveal>

      <section className="vision" aria-labelledby="vision-h">
        <Reveal>
          <p className="eyebrow">{t("land.whyEyebrow")}</p>
          <h2 id="vision-h" className="big serif">
            {t("land.whyH")}
          </h2>
          <p className="lede">{t("land.whyBody")}</p>
        </Reveal>
        <Reveal delay={140} className="vision-card">
          <p className="eyebrow">{t("land.visionEyebrow")}</p>
          <p className="vision-line serif">{t("land.visionBody")}</p>
          <p className="muted small">{t("land.prototype")}</p>
        </Reveal>
      </section>

      <Reveal className="cta-band">
        <h2 className="serif">{t("land.ctaH")}</h2>
        <div className="row center">
          <button className="btn" onClick={start}>
            {t("land.create")}
          </button>
          {bot}
        </div>
      </Reveal>
    </>
  );
}
