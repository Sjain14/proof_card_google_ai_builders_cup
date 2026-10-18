import "@fontsource-variable/inter";
import "@fontsource/instrument-serif/400.css";
import "@fontsource/instrument-serif/400-italic.css";
import "@fontsource-variable/jetbrains-mono";
import "./styles.css";
import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { devMode, signIn, signOut, watchUser } from "./auth";
import { Brief } from "./pages/Brief";
import { How } from "./pages/How";
import { BOT, Landing } from "./pages/Landing";
import { Library } from "./pages/Library";
import { Live } from "./pages/Live";
import { NewBrief } from "./pages/NewBrief";
import { Watch } from "./pages/Watch";
import { navigate, usePath } from "./router";
import { t } from "./i18n";
import { useAppStore } from "./store";

// Home page only (Team lead VN, 18 Oct): report an issue, the Telegram bot, the demo video.
// "Report an issue" is a plain server page (/v/report), same form and store as card reports.
const DEMO_VIDEO = "https://youtu.be/KappheB43Y4";
const ICON = { width: 15, height: 15, viewBox: "0 0 24 24", "aria-hidden": true } as const;

function FootLinks() {
  return (
    <nav className="foot-links" aria-label={t("foot.linksLabel")}>
      <a href="/v/report">
        <svg {...ICON} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 22V4m0 0h12l-2 4 2 4H4" />
        </svg>
        {t("foot.report")}
      </a>
      <a href={`https://t.me/${BOT}`} target="_blank" rel="noopener noreferrer">
        <svg {...ICON} fill="currentColor">
          <path d="M21.9 4.6 18.7 19.8c-.2 1-.9 1.3-1.8.8l-4.9-3.6-2.4 2.3c-.3.3-.5.5-1 .5l.3-5 9.2-8.3c.4-.4-.1-.6-.6-.2L6.2 13.4l-4.9-1.5c-1-.3-1.1-1 .2-1.5L20.6 3c.9-.3 1.6.2 1.3 1.6Z" />
        </svg>
        {t("foot.telegram")}
      </a>
      <a href={DEMO_VIDEO} target="_blank" rel="noopener noreferrer">
        <svg {...ICON} fill="currentColor">
          <path d="M23 7.2a3 3 0 0 0-2.1-2.1C19 4.6 12 4.6 12 4.6s-7 0-8.9.5A3 3 0 0 0 1 7.2 31 31 0 0 0 .5 12a31 31 0 0 0 .5 4.8 3 3 0 0 0 2.1 2.1c1.9.5 8.9.5 8.9.5s7 0 8.9-.5a3 3 0 0 0 2.1-2.1 31 31 0 0 0 .5-4.8 31 31 0 0 0-.5-4.8ZM9.8 15.1V8.9l5.7 3.1-5.7 3.1Z" />
        </svg>
        {t("foot.video")}
      </a>
    </nav>
  );
}

function App() {
  const path = usePath();
  const lang = useAppStore((s) => s.lang);
  const toggleLang = useAppStore((s) => s.toggleLang);
  const user = useAppStore((s) => s.user);
  const setUser = useAppStore((s) => s.setUser);

  useEffect(() => watchUser(setUser), [setUser]);

  const brief = path.match(/^\/s\/([A-Za-z0-9_-]{8,64})$/);
  const live = path.match(/^\/s\/([A-Za-z0-9_-]{8,64})\/live$/);
  const watch = path.match(/^\/watch\/([A-Za-z0-9_-]{8,64})$/);
  let page;
  if (watch?.[1]) page = <Watch id={watch[1]} />;
  else if (live?.[1]) page = <Live id={live[1]} user={user} />;
  else if (brief?.[1]) page = <Brief id={brief[1]} user={user} />;
  else if (path === "/new") page = <NewBrief user={user} />;
  else if (path === "/how") page = <How user={user} />;
  else if (path === "/cards") page = <Library />;
  else page = <Landing user={user} />;

  return (
    <>
      <header className="nav">
        <a
          className="logo"
          href="/"
          aria-label="Proof Card"
          onClick={(e) => {
            e.preventDefault();
            navigate("/");
          }}
        >
          <img src="/favicon.svg" alt="" width={26} height={26} />
          <span className="logo-word">Proof Card</span>
        </a>
        <div className="nav-right">
          <a
            className={`btn small ghost nav-lib${path === "/cards" ? " on" : ""}`}
            href="/cards"
            aria-current={path === "/cards" ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              navigate("/cards");
            }}
          >
            <span className="nav-lib-full">{t("nav.library")}</span>
            <span className="nav-lib-short">{t("nav.libraryShort")}</span>
          </a>
          <a
            className={`btn small nav-how${path === "/how" ? " on" : ""}`}
            href="/how"
            aria-current={path === "/how" ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              navigate("/how");
            }}
          >
            <span aria-hidden="true">?</span> {t("nav.how")}
          </a>
          <button
            className="link lang-toggle"
            lang={lang === "en" ? "hi" : "en"}
            aria-label={t("nav.langLabel")}
            onClick={toggleLang}
          >
            {lang === "en" ? "हिंदी" : "English"}
          </button>
          {devMode && <span className="chip">{t("nav.dev")}</span>}
          {user && !devMode && (
            <button className="link" onClick={() => void signOut()}>
              {t("nav.signOut")}
            </button>
          )}
          {user === null && (
            <button className="btn small" onClick={() => void signIn()}>
              {t("nav.signIn")}
            </button>
          )}
        </div>
      </header>
      <main>{page}</main>
      <footer className="foot">
        {path === "/" && <FootLinks />}
        {t("foot")}
      </footer>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
