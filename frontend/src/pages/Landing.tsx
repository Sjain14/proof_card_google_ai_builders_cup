import type { SignedIn } from "../auth";
import { signIn } from "../auth";
import { VerdictPill } from "../components/VerdictPill";
import { navigate } from "../router";

// Illustrative hero cards: design samples, not checked facts (labelled on screen).
const SAMPLES = [
  { v: "FALSE", claim: "“Every village got broadband last year.”", why: "Official tracker shows a fraction connected." },
  { v: "TRUE", claim: "“India's Constitution lists 22 scheduled languages.”", why: "Eighth Schedule, Constitution of India." },
  { v: "MISLEADING", claim: "“Petrol is cheapest here in all of Asia.”", why: "True for one month, not the year." },
] as const;

export function Landing({ user }: { user: SignedIn | null | undefined }) {
  const start = () => (user ? navigate("/new") : void signIn().then(() => navigate("/new")));
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Prebunk · Live · Proof that travels</p>
          <h1>
            Know the claim <em>before</em> it's said.
          </h1>
          <p className="lede">
            Give us a speech topic. Gemini predicts the claims, checks each against real sources, and
            stores the exact page it read. When a card gets forwarded and edited, we catch it.
          </p>
          <div className="row">
            <button className="btn" onClick={start}>
              Create a brief
            </button>
            <a className="btn ghost" href="#how">
              How it works
            </a>
          </div>
        </div>
        <div className="stack" aria-label="Example Proof Cards (illustrative)">
          {SAMPLES.map((s, i) => (
            <article key={s.v} className={`mini mini-${i}`}>
              <VerdictPill verdict={s.v} />
              <p className="mini-claim">{s.claim}</p>
              <p className="mini-why">{s.why}</p>
              <span className="mini-foot">illustrative</span>
            </article>
          ))}
        </div>
      </section>

      <section id="how" className="steps">
        <Step n="01" title="Before" body="Predict the 12 claims a speaker is likely to make and check them in advance, with sources and a stored snapshot of every page." />
        <Step n="02" title="During" body="When a predicted claim is spoken, its card is already there. New claims are checked live." />
        <Step n="03" title="After" body="Every card has a QR and a fingerprint. Forward it to our Telegram bot: VERIFIED, or ALTERED with what changed." />
      </section>

      <section className="trust">
        <h2>The model never has the last word.</h2>
        <p>
          We fetch every source ourselves, match the exact passage, and hash the page bytes. If the
          passage doesn't back the verdict, the card says <strong>Not enough proof</strong>. No
          forced true or false.
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
