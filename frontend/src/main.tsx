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
import { Landing } from "./pages/Landing";
import { Library } from "./pages/Library";
import { Live } from "./pages/Live";
import { NewBrief } from "./pages/NewBrief";
import { Watch } from "./pages/Watch";
import { navigate, usePath } from "./router";
import { t } from "./i18n";
import { useAppStore } from "./store";

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
