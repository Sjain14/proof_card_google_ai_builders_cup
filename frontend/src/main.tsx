import "@fontsource-variable/inter";
import "./styles.css";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { devMode, signIn, signOut, watchUser, type SignedIn } from "./auth";
import { Brief } from "./pages/Brief";
import { Landing } from "./pages/Landing";
import { Live } from "./pages/Live";
import { NewBrief } from "./pages/NewBrief";
import { navigate, usePath } from "./router";
import { getLang, setLang, t } from "./i18n";

function App() {
  const path = usePath();
  const [user, setUser] = useState<SignedIn | null | undefined>(undefined);
  useEffect(() => watchUser(setUser), []);
  const [lang, setLangState] = useState(getLang());
  useEffect(() => setLang(lang), [lang]);

  const brief = path.match(/^\/s\/([A-Za-z0-9_-]{8,64})$/);
  const live = path.match(/^\/s\/([A-Za-z0-9_-]{8,64})\/live$/);
  let page;
  if (live?.[1]) page = <Live id={live[1]} user={user} />;
  else if (brief?.[1]) page = <Brief id={brief[1]} user={user} />;
  else if (path === "/new") page = <NewBrief user={user} />;
  else page = <Landing user={user} />;

  return (
    <>
      <header className="nav">
        <a
          className="logo"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate("/");
          }}
        >
          <img src="/favicon.svg" alt="" width={26} height={26} />
          Proof Card
        </a>
        <div className="nav-right">
          <button
            className="link"
            lang={lang === "en" ? "hi" : "en"}
            aria-label={t("nav.langLabel")}
            onClick={() => setLangState(lang === "en" ? "hi" : "en")}
          >
            {t("nav.lang")}
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
      <main key={lang}>{page}</main>
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
