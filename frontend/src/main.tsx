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

function App() {
  const path = usePath();
  const [user, setUser] = useState<SignedIn | null | undefined>(undefined);
  useEffect(() => watchUser(setUser), []);

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
          {devMode && <span className="chip">local dev</span>}
          {user && !devMode && (
            <button className="link" onClick={() => void signOut()}>
              Sign out
            </button>
          )}
          {user === null && (
            <button className="btn small" onClick={() => void signIn()}>
              Sign in
            </button>
          )}
        </div>
      </header>
      <main>{page}</main>
      <footer className="foot">
        Built with Gemini on Vertex AI, Cloud Run, Firestore and Firebase. Proof that travels.
      </footer>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
