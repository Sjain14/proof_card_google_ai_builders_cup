import type { SignedIn } from "../auth";
import { signIn } from "../auth";
import { VerdictPill } from "../components/VerdictPill";
import { navigate } from "../router";
import { t } from "../i18n";

// Illustrative hero cards: design samples, not checked facts (labelled on screen).
const SAMPLES = [
  { v: "FALSE", claim: "land.s1.claim", why: "land.s1.why" },
  { v: "TRUE", claim: "land.s2.claim", why: "land.s2.why" },
  { v: "MISLEADING", claim: "land.s3.claim", why: "land.s3.why" },
] as const;

export function Landing({ user }: { user: SignedIn | null | undefined }) {
  const start = () => (user ? navigate("/new") : void signIn().then(() => navigate("/new")));
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">{t("land.eyebrow")}</p>
          <h1>
            {t("land.h1a")}<em>{t("land.h1b")}</em>{t("land.h1c")}
          </h1>
          <p className="lede">
            {t("land.lede")}
          </p>
          <div className="row">
            <button className="btn" onClick={start}>
              {t("land.create")}
            </button>
            <a className="btn ghost" href="#how">
              {t("land.how")}
            </a>
          </div>
        </div>
        <div className="stack" aria-label={t("land.samples")}>
          {SAMPLES.map((s, i) => (
            <article key={s.v} className={`mini mini-${i}`}>
              <VerdictPill verdict={s.v} />
              <p className="mini-claim">{t(s.claim)}</p>
              <p className="mini-why">{t(s.why)}</p>
              <span className="mini-foot">{t("land.illustrative")}</span>
            </article>
          ))}
        </div>
      </section>

      <section id="how" className="steps">
        <Step n="01" title={t("land.before")} body={t("land.beforeBody")} />
        <Step n="02" title={t("land.during")} body={t("land.duringBody")} />
        <Step n="03" title={t("land.after")} body={t("land.afterBody")} />
      </section>

      <section className="trust">
        <h2>{t("land.trustH")}</h2>
        <p>
          {t("land.trust1")}
          <strong>{t("verdict.UNVERIFIABLE")}</strong>
          {t("land.trust2")}
        </p>
      </section>
    </>
  );
}

function Step({ n, title, body }: { n: string; title: string; body: string }) {
  return (
    <div className="step">
      <span className="step-n">{n}</span>
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}
