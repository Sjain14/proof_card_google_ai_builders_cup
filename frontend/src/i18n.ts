// UI language: English + Hindi. No dependency (AGENTS.md §2): one flat dictionary, the
// Hindi table is typed against the English keys so a missing string fails `tsc`.
// Default: saved choice, else the browser language (hi* -> Hindi), else English.
// Card content (claim, explanation, sources) stays in the language it was checked in.

const en = {
  "nav.signIn": "Sign in",
  "nav.signOut": "Sign out",
  "nav.dev": "local dev",
  "nav.lang": "हिंदी",
  "nav.langLabel": "Switch to Hindi",
  foot: "Built with Gemini on Vertex AI, Cloud Run, Firestore and Firebase. Proof that travels.",

  "land.eyebrow": "Prebunk · Live · Proof that travels",
  "land.h1a": "Know the claim ",
  "land.h1b": "before",
  "land.h1c": " it's said.",
  "land.lede":
    "Give us a speech topic. Gemini predicts the claims, checks each against real sources, and stores the exact page it read. When a card gets forwarded and edited, we catch it.",
  "land.create": "Create a brief",
  "land.how": "How it works",
  "land.samples": "Example Proof Cards (illustrative)",
  "land.illustrative": "illustrative",
  "land.s1.claim": "“Every village got broadband last year.”",
  "land.s1.why": "Official tracker shows a fraction connected.",
  "land.s2.claim": "“India's Constitution lists 22 scheduled languages.”",
  "land.s2.why": "Eighth Schedule, Constitution of India.",
  "land.s3.claim": "“Petrol is cheapest here in all of Asia.”",
  "land.s3.why": "True for one month, not the year.",
  "land.before": "Before",
  "land.beforeBody":
    "Predict the 12 claims a speaker is likely to make and check them in advance, with sources and a stored snapshot of every page.",
  "land.during": "During",
  "land.duringBody": "When a predicted claim is spoken, its card is already there. New claims are checked live.",
  "land.after": "After",
  "land.afterBody":
    "Every card has a QR and a fingerprint. Forward it to our Telegram bot: VERIFIED, or ALTERED with what changed.",
  "land.trustH": "The model never has the last word.",
  "land.trust1":
    "We fetch every source ourselves, match the exact passage, and hash the page bytes. If the passage doesn't back the verdict, the card says ",
  "land.trust2": ". No forced true or false.",

  "new.signInH": "Sign in to create a brief",
  "new.signInBody": "Briefs are private to you. Cards you share are public.",
  "new.signInBtn": "Sign in with Google",
  "new.guestBtn": "Continue as guest",
  "new.eyebrow": "New brief",
  "new.h1": "What's the speech about?",
  "new.topic": "Topic",
  "new.required": "required",
  "new.topicPh": "e.g. Budget speech on fuel, jobs and digital India",
  "new.speaker": "Speaker",
  "new.youtube": "YouTube link",
  "new.links": "Context links",
  "new.linksHint": "up to 5, space separated",
  "new.network": "Network error, try again.",
  "new.starting": "Starting…",
  "new.generate": "Generate brief",
  "new.sample": "Try a sample topic",

  "brief.none": "No such brief.",
  "brief.loadFail": "Couldn't load.",
  "brief.loading": "Loading brief…",
  "brief.eyebrow": "Prebunk brief",
  "brief.predicting": "Predicting claims…",
  "brief.failed": "Couldn't build this brief. Start a new one.",
  "brief.progress": "{done} of {total} checked",
  "brief.ready": "{total} claims ready",
  "brief.goLive": "Go live",

  "tile.checking": "Checking sources…",
  "tile.couldnt": "Couldn't check",
  "tile.noSource": "No source we could fetch backed or refuted this. We show that instead of guessing.",
  "tile.live": "LIVE",
  "tile.prebunked": "PREBUNKED",
  "tile.support": "support",
  "tile.proof": "Proof",
  "tile.copied": "Copied",
  "tile.copy": "Copy link",

  "live.loading": "Loading…",
  "live.loadFail": "Couldn't load this brief.",
  "live.audioUnavailable": "Live audio needs the cloud model. Type the line below instead.",
  "live.wrong": "Something went wrong.",
  "live.owner": "Sign in as the owner of this brief to go live.",
  "live.unreachable": "Couldn't reach the live service.",
  "live.shareTab": "Pick this tab and tick “Share tab audio” to listen.",
  "live.eyebrow": "Live · {n} claims prebunked",
  "live.instant": "instant",
  "live.checkedLive": "checked live",
  "live.fastest": "fastest {ms} ms",
  "live.videoTitle": "Video being fact checked",
  "live.noVideo": "No video on this brief. Play the stream in this tab, then listen.",
  "live.stop": "Stop listening",
  "live.connecting": "Connecting…",
  "live.start": "Start listening",
  "live.heard": "Heard: “{text}”",
  "live.skip.not_checkable": "no checkable fact in it",
  "live.skip.repeat": "already on screen",
  "live.skip.error": "couldn't check this line, say it again",
  "live.privacy": "We listen to this tab only. Nothing is recorded.",
  "live.linePh": "Or type a line the speaker said",
  "live.lineLabel": "Line the speaker said",
  "live.check": "Check",
  "live.clip": "Or upload a recorded clip (audio, up to 15 min / 20 MB)",
  "live.clipLabel": "Recorded audio clip",
  "live.clipBig": "Clip is over 20 MB. Trim it and try again.",
  "live.clipWorking": "Transcribing the clip and checking every line…",
  "live.clipDone": "Clip done: {n} lines checked.",
  "live.clipFail": "Couldn't process the clip.",
  "live.tg": "Get FALSE / MISLEADING alerts on Telegram",
  "live.tgOpen": "Telegram opened: tap Start in the bot chat to switch alerts on.",
  "live.empty": "Claims appear here the moment they're said. Prebunked ones arrive instantly.",

  "verdict.TRUE": "True",
  "verdict.MISLEADING": "Misleading",
  "verdict.FALSE": "False",
  "verdict.UNVERIFIABLE": "Not enough proof",
};

export type Key = keyof typeof en;

const hi: Record<Key, string> = {
  "nav.signIn": "साइन इन",
  "nav.signOut": "साइन आउट",
  "nav.dev": "लोकल डेव",
  "nav.lang": "English",
  "nav.langLabel": "अंग्रेज़ी में देखें",
  foot: "Vertex AI पर Gemini, Cloud Run, Firestore और Firebase से बना। सबूत जो साथ चलता है।",

  "land.eyebrow": "पहले से जाँच · लाइव · सबूत जो साथ चलता है",
  "land.h1a": "दावा बोले जाने से ",
  "land.h1b": "पहले",
  "land.h1c": " ही जानिए।",
  "land.lede":
    "भाषण का विषय बताइए। Gemini उसमें आने वाले दावों का अनुमान लगाता है, हर दावे को असली स्रोतों से जाँचता है, और जो पेज पढ़ा उसे ज्यों का त्यों सहेजता है। कार्ड आगे भेजकर बदला गया तो हम पकड़ लेते हैं।",
  "land.create": "ब्रीफ़ बनाइए",
  "land.how": "यह कैसे काम करता है",
  "land.samples": "प्रूफ़ कार्ड के उदाहरण (सिर्फ़ नमूना)",
  "land.illustrative": "नमूना",
  "land.s1.claim": "“पिछले साल हर गाँव में ब्रॉडबैंड पहुँच गया।”",
  "land.s1.why": "सरकारी ट्रैकर में कुछ ही गाँव जुड़े दिखते हैं।",
  "land.s2.claim": "“भारत के संविधान में 22 अनुसूचित भाषाएँ हैं।”",
  "land.s2.why": "आठवीं अनुसूची, भारत का संविधान।",
  "land.s3.claim": "“पूरे एशिया में पेट्रोल यहीं सबसे सस्ता है।”",
  "land.s3.why": "एक महीने के लिए सही, पूरे साल के लिए नहीं।",
  "land.before": "पहले",
  "land.beforeBody":
    "वक्ता जो 12 दावे कर सकता है उनका अनुमान लगाइए और पहले ही जाँच लीजिए, स्रोतों के साथ और हर पेज की सहेजी हुई कॉपी के साथ।",
  "land.during": "दौरान",
  "land.duringBody": "अनुमानित दावा बोलते ही उसका कार्ड तैयार मिलता है। नए दावे लाइव जाँचे जाते हैं।",
  "land.after": "बाद में",
  "land.afterBody":
    "हर कार्ड पर QR और फ़िंगरप्रिंट है। उसे हमारे Telegram बॉट को भेजिए: VERIFIED, या ALTERED और क्या बदला गया।",
  "land.trustH": "आख़िरी फ़ैसला कभी मॉडल का नहीं।",
  "land.trust1":
    "हर स्रोत हम ख़ुद खोलते हैं, ठीक वही अंश मिलाते हैं, और पेज के बाइट्स का हैश रखते हैं। अगर अंश फ़ैसले का समर्थन नहीं करता, तो कार्ड पर लिखा आता है ",
  "land.trust2": "। ज़बरदस्ती सही या गलत नहीं।",

  "new.signInH": "ब्रीफ़ बनाने के लिए साइन इन कीजिए",
  "new.signInBody": "ब्रीफ़ सिर्फ़ आपके लिए हैं। जो कार्ड आप शेयर करते हैं वे सार्वजनिक हैं।",
  "new.signInBtn": "Google से साइन इन",
  "new.guestBtn": "अतिथि के रूप में जारी रखें",
  "new.eyebrow": "नया ब्रीफ़",
  "new.h1": "भाषण किस बारे में है?",
  "new.topic": "विषय",
  "new.required": "ज़रूरी",
  "new.topicPh": "जैसे: ईंधन, नौकरियों और डिजिटल इंडिया पर बजट भाषण",
  "new.speaker": "वक्ता",
  "new.youtube": "YouTube लिंक",
  "new.links": "संदर्भ लिंक",
  "new.linksHint": "ज़्यादा से ज़्यादा 5, स्पेस से अलग",
  "new.network": "नेटवर्क में दिक्कत, दोबारा कोशिश कीजिए।",
  "new.starting": "शुरू हो रहा है…",
  "new.generate": "ब्रीफ़ बनाइए",
  "new.sample": "एक नमूना विषय आज़माइए",

  "brief.none": "ऐसा कोई ब्रीफ़ नहीं है।",
  "brief.loadFail": "लोड नहीं हो सका।",
  "brief.loading": "ब्रीफ़ लोड हो रहा है…",
  "brief.eyebrow": "पहले से जाँच का ब्रीफ़",
  "brief.predicting": "दावों का अनुमान लग रहा है…",
  "brief.failed": "यह ब्रीफ़ नहीं बन सका। नया ब्रीफ़ शुरू कीजिए।",
  "brief.progress": "{total} में से {done} जाँचे गए",
  "brief.ready": "{total} दावे तैयार",
  "brief.goLive": "लाइव जाइए",

  "tile.checking": "स्रोत जाँचे जा रहे हैं…",
  "tile.couldnt": "जाँच नहीं हो सकी",
  "tile.noSource": "जो स्रोत हम खोल पाए उनमें से किसी ने इसे सही या गलत साबित नहीं किया। अंदाज़ा लगाने की बजाय हम यही दिखाते हैं।",
  "tile.live": "लाइव",
  "tile.prebunked": "पहले से जाँचा",
  "tile.support": "समर्थन",
  "tile.proof": "सबूत",
  "tile.copied": "कॉपी हो गया",
  "tile.copy": "लिंक कॉपी करें",

  "live.loading": "लोड हो रहा है…",
  "live.loadFail": "यह ब्रीफ़ लोड नहीं हो सका।",
  "live.audioUnavailable": "लाइव ऑडियो के लिए क्लाउड मॉडल चाहिए। नीचे लाइन टाइप कीजिए।",
  "live.wrong": "कुछ गड़बड़ हो गई।",
  "live.owner": "लाइव जाने के लिए इस ब्रीफ़ के मालिक के रूप में साइन इन कीजिए।",
  "live.unreachable": "लाइव सेवा तक नहीं पहुँच सके।",
  "live.shareTab": "सुनने के लिए यही टैब चुनिए और “Share tab audio” पर टिक कीजिए।",
  "live.eyebrow": "लाइव · {n} दावे पहले से जाँचे",
  "live.instant": "तुरंत",
  "live.checkedLive": "लाइव जाँचे",
  "live.fastest": "सबसे तेज़ {ms} ms",
  "live.videoTitle": "जिस वीडियो की जाँच हो रही है",
  "live.noVideo": "इस ब्रीफ़ में वीडियो नहीं है। स्ट्रीम इसी टैब में चलाइए, फिर सुनिए।",
  "live.stop": "सुनना बंद करें",
  "live.connecting": "जुड़ रहा है…",
  "live.start": "सुनना शुरू करें",
  "live.heard": "सुना: “{text}”",
  "live.skip.not_checkable": "इसमें जाँचने लायक तथ्य नहीं",
  "live.skip.repeat": "पहले से स्क्रीन पर है",
  "live.skip.error": "यह लाइन जाँच नहीं पाए, फिर से बोलिए",
  "live.privacy": "हम सिर्फ़ यही टैब सुनते हैं। कुछ भी रिकॉर्ड नहीं होता।",
  "live.linePh": "या वक्ता की कही लाइन टाइप कीजिए",
  "live.lineLabel": "वक्ता की कही लाइन",
  "live.check": "जाँचें",
  "live.clip": "या रिकॉर्ड की हुई क्लिप अपलोड कीजिए (ऑडियो, 15 मिनट / 20 MB तक)",
  "live.clipLabel": "रिकॉर्ड की हुई ऑडियो क्लिप",
  "live.clipBig": "क्लिप 20 MB से बड़ी है। छोटी करके दोबारा कोशिश कीजिए।",
  "live.clipWorking": "क्लिप लिखी जा रही है और हर लाइन जाँची जा रही है…",
  "live.clipDone": "क्लिप पूरी: {n} लाइनें जाँची गईं।",
  "live.clipFail": "क्लिप प्रोसेस नहीं हो सकी।",
  "live.tg": "गलत / भ्रामक दावों के अलर्ट Telegram पर पाएं",
  "live.tgOpen": "Telegram खुल गया: अलर्ट चालू करने के लिए बॉट चैट में Start दबाएं।",
  "live.empty": "दावे बोलते ही यहाँ दिखते हैं। पहले से जाँचे दावे तुरंत आते हैं।",

  // Same words as the card image and share page (context/05_UI_UX.md §3, verdict.ts).
  "verdict.TRUE": "सही",
  "verdict.MISLEADING": "भ्रामक",
  "verdict.FALSE": "गलत",
  "verdict.UNVERIFIABLE": "पुख्ता सबूत नहीं",
};

export type Lang = "en" | "hi";
export const DICTS: Record<Lang, Record<Key, string>> = { en, hi };
const STORE_KEY = "pc.lang";

export function initialLang(saved: string | null, browser: readonly string[] = []): Lang {
  if (saved === "en" || saved === "hi") return saved;
  const primary = browser[0]?.toLowerCase() ?? "";
  return primary.startsWith("hi") ? "hi" : "en";
}

let current: Lang = typeof window === "undefined" ? "en" : initialLang(safeGet(), navigator.languages ?? []);

function safeGet(): string | null {
  try {
    const raw = localStorage.getItem("proofcard_app_store");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed?.state?.lang === "hi" || parsed?.state?.lang === "en") {
        return parsed.state.lang;
      }
    }
    return localStorage.getItem(STORE_KEY);
  } catch {
    return null;
  }
}

export function getLang(): Lang {
  return current;
}

export function setLang(lang: Lang): void {
  current = lang;
  try {
    localStorage.setItem(STORE_KEY, lang);
  } catch {
    /* private mode: choice lasts this page only */
  }
  if (typeof document !== "undefined") document.documentElement.lang = lang;
}

export function format(s: string, vars: Record<string, string | number> = {}): string {
  return s.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

export function t(key: Key, vars?: Record<string, string | number>): string {
  return format(DICTS[current][key], vars);
}
