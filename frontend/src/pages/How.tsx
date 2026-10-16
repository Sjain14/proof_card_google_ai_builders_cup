import { useEffect, useRef, useState, type ReactNode } from "react";
import type { SignedIn } from "../auth";
import { signIn } from "../auth";
import { VerdictPill } from "../components/VerdictPill";
import { getLang } from "../i18n";
import { navigate } from "../router";
import { SAMPLE, SAMPLE_VIDEO_ID } from "../sample";
import { BOT, Qr, Reveal, demoHash } from "./Landing";

// How to use: one real sample (the Trump clip) walked step by step. Each step is a short
// line plus a small mock of the actual screen; the mock stays pinned while the steps
// scroll past (Stripe / Linear docs pattern). Under 900 px the mock sits inline instead.
// Copy is en + hi here (page scoped) so the shared dictionary stays small.

type Step = { h: string; b: string; tip?: string };

const EN = {
  eyebrow: "How to use",
  h1: "From a speech to proof anyone can check",
  lede: "Three ways in. Pick yours, or follow the Trump sample end to end: every step below is the real screen.",
  pathSpeech: "Check a speech or video",
  pathSpeechB: "YouTube link, recorded or live",
  pathTg: "Check a forward on Telegram",
  pathTgB: "text, screenshot or long message",
  pathCard: "Got a Proof Card?",
  pathCardB: "see the proof, spot an edited copy",
  trySample: "Try the Trump sample",
  openBot: "Open the Telegram bot",
  example: "example",
  speechH: "Check a speech",
  speech: [
    { h: "Open “Check a speech”", b: "Sign in with Google or continue as a guest. Your briefs stay private; cards you share are public." },
    { h: "Paste the YouTube link", b: "That is all it needs: the title becomes the topic. Or press “Fill the Trump sample” and every field is filled for you.", tip: "Speaker and context links are optional. They sharpen the research." },
    { h: "The brief prepares", b: "We predict the claims likely to come up, pull official figures (World Bank, ministries, statistics offices) into a fact bank, and check each claim. Cards land one by one." },
    { h: "Recorded video or scheduled live?", b: "Recorded: open the live page and press “Check the sample clip” (or upload any audio clip) and every line is checked. Scheduled live: make the brief before it starts, then open the live page when it goes live, play it there and press Start listening." },
    { h: "Cards pop as it's said", b: "A claim the brief already proved shows instantly (PREBUNKED). A new one is checked live (LIVE). Replay mode pops each card at the second it's said in the video." },
    { h: "Open the proof, share the card", b: "Every card shows the exact passage that decides it and the source page we stored. Its fingerprint changes if anyone edits the card. Share the link, the image or send it on Telegram." },
  ] as Step[],
  tgH: "Check anything on Telegram",
  tg: [
    { h: "Send a claim", b: "Type or paste one line. The bot answers “Checking…” at once, then the verdict card with its proof link." },
    { h: "Forward a message or a screenshot", b: "Forward a long WhatsApp-style message or a screenshot of one. The bot reads it, finds up to 3 checkable claims and answers each." },
    { h: "Use it in groups", b: "Add the bot to a family or office group. It stays quiet, and checks only forwards, messages that tag it, or /check." },
    { h: "Did they really say it?", b: "“Modi said: …” is first checked as a quote: is it on record? On record means TRUE for the quote (not for what's inside it); reworded means MISLEADING." },
  ] as Step[],
  cardH: "Got a Proof Card forwarded?",
  card: [
    { h: "Open its link or scan its QR", b: "It opens the card's page: the verdict, the passage, the source and when we fetched it. You never type a card id; it's inside the link and the QR." },
    { h: "Check a copy you received", b: "Upload the image on the card page, or forward it to the bot. VERIFIED means it's the original. ALTERED means someone edited it, and the real card is shown." },
  ] as Step[],
  faqH: "Quick answers",
  faq: [
    ["What is the card id for?", "It's the card's address: proofcard/v/<id>. It's in every link and QR, so you never copy or type it. The bot reads it from the image."],
    ["Recorded video vs live stream?", "Recorded: paste the link, then check the clip (one click for the sample, or upload its audio). Live: create the brief before the stream starts so the claims are ready, then listen on the live page while it plays."],
    ["What does “Not enough proof” mean?", "No source we could fetch decided it. We say so instead of guessing."],
    ["Is a claim checked twice?", "No. Every verified card is saved; the same claim again gets the saved card at once."],
  ] as [string, string][],
  ctaH: "Try it on the Trump sample",
  ctaB: "One click fills the form. One click checks the clip.",
  you: "you",
  bot: "Proof Card bot",
  checking: "Checking this claim against official data and trusted sources…",
  open: "Open proof",
  found: "Found 2 checkable claims in this forward. Checking each…",
  screenshot: "screenshot",
  forwarded: "Forwarded",
  quiet: "chat in the group, the bot stays quiet",
  quoteWhy: "On record: he did say this. This card proves the quote, not the statement.",
  signGoogle: "Sign in with Google",
  guest: "Continue as guest",
  fill: "Fill the Trump sample",
  generate: "Generate brief",
  bank: "fact bank: official figures",
  recorded: "Recorded video",
  recordedB: "Check the sample clip",
  live: "Scheduled live",
  liveB1: "Before: create the brief",
  liveB2: "When it starts: Start listening",
  instant: "instant",
  passage: "passage",
  fingerprint: "fingerprint",
  copy: "Copy link",
  verified: "VERIFIED: this is the original card",
  altered: "ALTERED: verdict was edited",
  c1: "We ended eight wars in eight months.",
  c2: "No president has ever done what I've done.",
  c3: "Trump has been nominated for the Nobel Peace Prize.",
  why1: "Records list fewer conflicts ended; several were ceasefires, not ended wars.",
};

type Copy = typeof EN;

const HI: Copy = {
  eyebrow: "इस्तेमाल कैसे करें",
  h1: "भाषण से ऐसे सबूत तक जिसे कोई भी जाँच सके",
  lede: "तीन रास्ते। अपना चुनिए, या ट्रंप वाला नमूना शुरू से अंत तक देखिए: नीचे हर कदम असली स्क्रीन है।",
  pathSpeech: "भाषण या वीडियो जाँचिए",
  pathSpeechB: "YouTube लिंक, रिकॉर्डेड या लाइव",
  pathTg: "Telegram पर फ़ॉरवर्ड जाँचिए",
  pathTgB: "टेक्स्ट, स्क्रीनशॉट या लंबा मैसेज",
  pathCard: "Proof Card मिला है?",
  pathCardB: "सबूत देखिए, बदली हुई कॉपी पकड़िए",
  trySample: "ट्रंप वाला नमूना आज़माइए",
  openBot: "Telegram बॉट खोलिए",
  example: "उदाहरण",
  speechH: "भाषण जाँचिए",
  speech: [
    { h: "“भाषण जाँचिए” खोलिए", b: "Google से साइन इन कीजिए या अतिथि के रूप में जारी रखिए। ब्रीफ़ सिर्फ़ आपके हैं; शेयर किए कार्ड सार्वजनिक हैं।" },
    { h: "YouTube लिंक डालिए", b: "बस इतना ही: शीर्षक ही विषय बन जाता है। या “ट्रंप नमूना भरिए” दबाइए, हर खाना भर जाएगा।", tip: "वक्ता और संदर्भ लिंक वैकल्पिक हैं, इनसे रिसर्च बेहतर होती है।" },
    { h: "ब्रीफ़ तैयार होता है", b: "हम संभावित दावे पहले से निकालते हैं, आधिकारिक आँकड़े (World Bank, मंत्रालय, सांख्यिकी दफ़्तर) फ़ैक्ट बैंक में जोड़ते हैं और हर दावा जाँचते हैं। कार्ड एक-एक कर आते हैं।" },
    { h: "रिकॉर्डेड वीडियो या आने वाला लाइव?", b: "रिकॉर्डेड: लाइव पेज खोलिए और “नमूना क्लिप जाँचिए” दबाइए (या कोई भी ऑडियो क्लिप डालिए), हर लाइन जाँची जाएगी। लाइव: शुरू होने से पहले ब्रीफ़ बनाइए, लाइव होने पर लाइव पेज खोलिए, वहीं चलाइए और “सुनना शुरू करें” दबाइए।" },
    { h: "बोलते ही कार्ड", b: "जो दावा ब्रीफ़ पहले ही साबित कर चुका है वह तुरंत दिखता है (PREBUNKED)। नया दावा उसी समय जाँचा जाता है (LIVE)। रिप्ले मोड में हर कार्ड वीडियो के उसी सेकंड पर आता है।" },
    { h: "सबूत खोलिए, कार्ड शेयर कीजिए", b: "हर कार्ड में फ़ैसला करने वाला असली अंश और हमारा सहेजा स्रोत पेज है। कोई कार्ड बदले तो उसका फ़िंगरप्रिंट बदल जाता है। लिंक, इमेज या Telegram से भेजिए।" },
  ],
  tgH: "Telegram पर कुछ भी जाँचिए",
  tg: [
    { h: "दावा भेजिए", b: "एक लाइन लिखिए या पेस्ट कीजिए। बॉट तुरंत “जाँच रहे हैं…” कहता है, फिर सबूत लिंक के साथ फ़ैसला।" },
    { h: "मैसेज या स्क्रीनशॉट फ़ॉरवर्ड कीजिए", b: "लंबा फ़ॉरवर्ड या उसका स्क्रीनशॉट भेजिए। बॉट उसे पढ़कर 3 तक जाँचने लायक दावे ढूँढता है और हर एक का जवाब देता है।" },
    { h: "ग्रुप में इस्तेमाल", b: "बॉट को परिवार या दफ़्तर के ग्रुप में जोड़िए। वह चुप रहता है, सिर्फ़ फ़ॉरवर्ड, टैग किए मैसेज या /check जाँचता है।" },
    { h: "क्या सच में ऐसा कहा?", b: "“मोदी ने कहा कि …” पहले कथन के रूप में जाँचा जाता है: क्या यह रिकॉर्ड में है? रिकॉर्ड में है तो कथन TRUE (अंदर की बात नहीं); शब्द बदले हैं तो MISLEADING।" },
  ],
  cardH: "किसी ने Proof Card भेजा है?",
  card: [
    { h: "लिंक खोलिए या QR स्कैन कीजिए", b: "कार्ड का पेज खुलता है: फ़ैसला, अंश, स्रोत और कब लिया गया। कार्ड id कभी टाइप नहीं करनी, वह लिंक और QR में है।" },
    { h: "मिली कॉपी जाँचिए", b: "कार्ड पेज पर इमेज अपलोड कीजिए या बॉट को फ़ॉरवर्ड कीजिए। VERIFIED यानी असली कार्ड। ALTERED यानी किसी ने बदला है, और असली कार्ड दिखता है।" },
  ],
  faqH: "छोटे जवाब",
  faq: [
    ["कार्ड id किस लिए है?", "यह कार्ड का पता है: proofcard/v/<id>। हर लिंक और QR में है, इसलिए कॉपी या टाइप नहीं करनी पड़ती। बॉट इमेज से पढ़ लेता है।"],
    ["रिकॉर्डेड वीडियो बनाम लाइव?", "रिकॉर्डेड: लिंक डालिए, फिर क्लिप जाँचिए (नमूने के लिए एक क्लिक, या उसका ऑडियो डालिए)। लाइव: स्ट्रीम से पहले ब्रीफ़ बनाइए ताकि दावे तैयार रहें, फिर चलते समय लाइव पेज पर सुनिए।"],
    ["“पुख्ता सबूत नहीं” का मतलब?", "जो स्रोत हम खोल पाए उनमें से किसी ने फ़ैसला नहीं किया। हम अंदाज़ा नहीं लगाते, यही बताते हैं।"],
    ["क्या एक दावा दो बार जाँचा जाता है?", "नहीं। हर जाँचा कार्ड सहेजा जाता है; वही दावा फिर आए तो सहेजा कार्ड तुरंत मिलता है।"],
  ] as [string, string][],
  ctaH: "ट्रंप वाले नमूने पर आज़माइए",
  ctaB: "एक क्लिक में फ़ॉर्म भरता है। एक क्लिक में क्लिप जाँचती है।",
  you: "आप",
  bot: "Proof Card बॉट",
  checking: "यह दावा आधिकारिक आँकड़ों और भरोसेमंद स्रोतों से जाँचा जा रहा है…",
  open: "सबूत खोलिए",
  found: "इस फ़ॉरवर्ड में 2 जाँचने लायक दावे मिले। हर एक जाँच रहे हैं…",
  screenshot: "स्क्रीनशॉट",
  forwarded: "फ़ॉरवर्ड किया गया",
  quiet: "ग्रुप में बातचीत, बॉट चुप रहता है",
  quoteWhy: "रिकॉर्ड में है: उन्होंने यह कहा था। यह कार्ड कथन साबित करता है, उसकी बात नहीं।",
  signGoogle: "Google से साइन इन",
  guest: "अतिथि के रूप में जारी रखें",
  fill: "ट्रंप नमूना भरिए",
  generate: "ब्रीफ़ बनाइए",
  bank: "फ़ैक्ट बैंक: आधिकारिक आँकड़े",
  recorded: "रिकॉर्डेड वीडियो",
  recordedB: "नमूना क्लिप जाँचिए",
  live: "आने वाला लाइव",
  liveB1: "पहले: ब्रीफ़ बनाइए",
  liveB2: "शुरू होने पर: सुनना शुरू करें",
  instant: "तुरंत",
  passage: "अंश",
  fingerprint: "फ़िंगरप्रिंट",
  copy: "लिंक कॉपी",
  verified: "VERIFIED: यह असली कार्ड है",
  altered: "ALTERED: फ़ैसला बदला गया",
  c1: "We ended eight wars in eight months.",
  c2: "No president has ever done what I've done.",
  c3: "Trump has been nominated for the Nobel Peace Prize.",
  why1: "रिकॉर्ड में कम संघर्ष खत्म हुए; कई सिर्फ़ युद्धविराम थे।",
};

function useCopy() {
  return (getLang() === "hi" ? HI : EN) as Copy;
}

const Cursor = () => (
  <svg className="hw-cursor" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M4 2l14 9-6.2 1.4L15 20l-3 1.4-3.3-7.4L4 18z" fill="#111827" stroke="#fff" strokeWidth="1.4" />
  </svg>
);

function Frame({ url, children }: { url: string; children: ReactNode }) {
  return (
    <div className="hw-frame">
      <div className="hw-bar">
        <i />
        <i />
        <i />
        <span className="mono">{url}</span>
      </div>
      <div className="hw-body">{children}</div>
    </div>
  );
}

function Chat({ children }: { children: ReactNode }) {
  return (
    <div className="vis tg hw-chat">
      <p className="hw-chat-h">@{BOT}</p>
      {children}
    </div>
  );
}

function SpeechVis({ n }: { n: number }) {
  const c = useCopy();
  if (n === 0)
    return (
      <Frame url="aibuilderscup.web.app">
        <p className="hw-h">{c.pathSpeech}</p>
        <span className="btn small hw-hot">
          {c.signGoogle}
          <Cursor />
        </span>
        <span className="btn small ghost">{c.guest}</span>
      </Frame>
    );
  if (n === 1)
    return (
      <Frame url="aibuilderscup.web.app/new">
        <span className="hw-field mono">{SAMPLE.youtube.replace("https://www.", "")}</span>
        <span className="hw-field">{SAMPLE.topic}</span>
        <span className="hw-field">{SAMPLE.speaker}</span>
        <div className="row">
          <span className="btn small">{c.generate}</span>
          <span className="btn small ghost hw-hot">
            {c.fill}
            <Cursor />
          </span>
        </div>
      </Frame>
    );
  if (n === 2)
    return (
      <Frame url="aibuilderscup.web.app/s/…">
        <p className="vis-cap">{c.bank} · World Bank · IMF · BLS</p>
        {[
          [c.c1, "FALSE"],
          [c.c2, "UNVERIFIABLE"],
          [c.c3, "TRUE"],
        ].map(([t, v], k) => (
          <div key={k} className="vis-row hw-row" style={{ animationDelay: `${k * 200}ms` }}>
            <VerdictPill verdict={v as "TRUE"} />
            <span>{t}</span>
          </div>
        ))}
      </Frame>
    );
  if (n === 3)
    return (
      <div className="hw-split">
        <div className="vis">
          <p className="vis-cap">{c.recorded}</p>
          <div className="hw-thumb">
            <img src={`https://i.ytimg.com/vi/${SAMPLE_VIDEO_ID}/mqdefault.jpg`} alt="" loading="lazy" />
            <span>▶</span>
          </div>
          <span className="btn small hw-hot">
            {c.recordedB}
            <Cursor />
          </span>
        </div>
        <div className="vis">
          <p className="vis-cap">{c.live}</p>
          <ol className="hw-steps">
            <li>{c.liveB1}</li>
            <li>
              <span className="live-dot" aria-hidden="true" /> {c.liveB2}
            </li>
          </ol>
        </div>
      </div>
    );
  if (n === 4)
    return (
      <div className="vis hw-feed">
        <div className="hw-feed-i">
          <span className="badge b-pre">PREBUNKED</span>
          <span className="latency">{c.instant}</span>
          <VerdictPill verdict="FALSE" />
          <p>“{c.c1}”</p>
        </div>
        <div className="hw-feed-i">
          <span className="badge b-live">LIVE</span>
          <VerdictPill verdict="UNVERIFIABLE" />
          <p>“{c.c2}”</p>
        </div>
      </div>
    );
  return (
    <div className="vis receipt">
      <VerdictPill verdict="FALSE" hindi />
      <p className="vis-claim">{c.c1}</p>
      <p className="hw-passage">
        <span className="mono label">{c.passage}</span> <mark>{c.why1}</mark>
      </p>
      <Qr seed="howto" />
      <p className="mono fp">
        {c.fingerprint} {demoHash("howto")}
      </p>
      <div className="row">
        <span className="btn small ghost">{c.copy}</span>
        <span className="btn small ghost">Telegram</span>
        <span className="btn small ghost">PNG</span>
      </div>
    </div>
  );
}

function TgVis({ n }: { n: number }) {
  const c = useCopy();
  const verdict = (
    <div className="bubble bot">
      <VerdictPill verdict="FALSE" />
      <span>{c.why1}</span>
      <span className="tg-btn">{c.open}</span>
    </div>
  );
  if (n === 0)
    return (
      <Chat>
        <div className="bubble me">{c.c1}</div>
        <div className="bubble bot hw-ack">{c.checking}</div>
        {verdict}
      </Chat>
    );
  if (n === 1)
    return (
      <Chat>
        <div className="bubble me">
          <span className="mono small">{c.forwarded}</span>
          <span className="hw-shot">📷 {c.screenshot}</span>
        </div>
        <div className="bubble bot hw-ack">{c.found}</div>
        {verdict}
      </Chat>
    );
  if (n === 2)
    return (
      <Chat>
        <div className="bubble hw-other">{c.quiet}</div>
        <div className="bubble me">
          <b>@{BOT}</b> {c.c1}
        </div>
        {verdict}
      </Chat>
    );
  return (
    <Chat>
      <div className="bubble me">Trump said: “{c.c1}”</div>
      <div className="bubble bot">
        <VerdictPill verdict="TRUE" />
        <span>{c.quoteWhy}</span>
        <span className="tg-btn">{c.open}</span>
      </div>
    </Chat>
  );
}

function CardVis({ n }: { n: number }) {
  const c = useCopy();
  if (n === 0)
    return (
      <Frame url={`aibuilderscup.web.app/v/${demoHash("id").slice(0, 12)}`}>
        <VerdictPill verdict="FALSE" hindi />
        <p className="vis-claim">“{c.c1}”</p>
        <p className="hw-passage">
          <span className="mono label">{c.passage}</span> <mark>{c.why1}</mark>
        </p>
      </Frame>
    );
  return (
    <div className="hw-split">
      <div className="vis hw-ok">✓ {c.verified}</div>
      <div className="vis hw-bad">✕ {c.altered}</div>
    </div>
  );
}

/** Steps scroll on the right; the matching screen stays pinned on the left. */
function Tour({ id, title, steps, Vis, start }: { id: string; title: string; steps: Step[]; Vis: (p: { n: number }) => ReactNode; start: number }) {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLDivElement | null)[]>([]);
  const c = useCopy();
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
  }, [steps.length]);
  return (
    <section id={id} className="hw-sec" aria-labelledby={`${id}-h`}>
      <Reveal>
        <h2 id={`${id}-h`} className="big serif">
          {title}
        </h2>
      </Reveal>
      <div className="how">
        <div className="how-pin" aria-hidden="true">
          <div className="how-frame">
            {steps.map((_, k) => (
              <div key={k} className={`how-vis ${k === active ? "on" : ""}`}>
                <Vis n={k} />
                <span className="hw-ex mono">{c.example}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="how-steps">
          {steps.map((s, k) => (
            <div
              key={k}
              data-n={k}
              ref={(el) => {
                refs.current[k] = el;
              }}
              className={`how-step ${k === active ? "on" : ""}`}
            >
              <span className="step-n mono">
                {String(start + k).padStart(2, "0")}
              </span>
              <h3>{s.h}</h3>
              <p>{s.b}</p>
              {s.tip && <p className="hw-tip">{s.tip}</p>}
              <div className="how-inline">
                <Vis n={k} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/** Thin bar under the nav: how far through the guide you are. */
function ScrollProgress() {
  const [p, setP] = useState(0);
  useEffect(() => {
    const on = () => {
      const max = document.documentElement.scrollHeight - innerHeight;
      setP(max > 0 ? Math.min(1, scrollY / max) : 0);
    };
    on();
    addEventListener("scroll", on, { passive: true });
    return () => removeEventListener("scroll", on);
  }, []);
  return <div className="hw-progress" style={{ transform: `scaleX(${p})` }} aria-hidden="true" />;
}

export function How({ user }: { user: SignedIn | null | undefined }) {
  const c = useCopy();
  const sample = () => (user ? navigate("/new?sample=trump") : void signIn().then(() => navigate("/new?sample=trump")));
  const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const botLink = `https://t.me/${BOT}?start=try`;
  return (
    <div className="hw">
      <ScrollProgress />
      <section className="hw-hero">
        <p className="eyebrow">{c.eyebrow}</p>
        <h1 className="serif">{c.h1}</h1>
        <p className="lede">{c.lede}</p>
        <div className="hw-paths">
          {(
            [
              ["speech", "01", c.pathSpeech, c.pathSpeechB],
              ["telegram", "02", c.pathTg, c.pathTgB],
              ["card", "03", c.pathCard, c.pathCardB],
            ] as const
          ).map(([id, n, h, b]) => (
            <button key={id} className="hw-path" onClick={() => jump(id)}>
              <span className="mono step-n">{n}</span>
              <b>{h}</b>
              <span className="muted">{b}</span>
              <span className="hw-arrow" aria-hidden="true">↓</span>
            </button>
          ))}
        </div>
        <div className="row">
          <button className="btn" onClick={sample}>
            {c.trySample}
          </button>
          <a className="btn ghost" href={botLink} target="_blank" rel="noreferrer">
            {c.openBot}
          </a>
        </div>
      </section>

      <Tour id="speech" title={c.speechH} steps={c.speech} Vis={SpeechVis} start={1} />
      <Tour id="telegram" title={c.tgH} steps={c.tg} Vis={TgVis} start={c.speech.length + 1} />
      <Tour id="card" title={c.cardH} steps={c.card} Vis={CardVis} start={c.speech.length + c.tg.length + 1} />

      <section className="hw-faq" aria-labelledby="faq-h">
        <h2 id="faq-h" className="serif">
          {c.faqH}
        </h2>
        {c.faq.map(([q, a]) => (
          <details key={q}>
            <summary>{q}</summary>
            <p>{a}</p>
          </details>
        ))}
      </section>

      <Reveal className="cta-band">
        <h2 className="serif">{c.ctaH}</h2>
        <p className="lede">{c.ctaB}</p>
        <div className="row center">
          <button className="btn" onClick={sample}>
            {c.trySample}
          </button>
          <a className="btn ghost" href={botLink} target="_blank" rel="noreferrer">
            {c.openBot}
          </a>
        </div>
      </Reveal>
    </div>
  );
}
