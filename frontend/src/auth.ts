// Firebase Auth (Google sign in). Docs: https://firebase.google.com/docs/auth/web/google-signin
// Config comes from VITE_FIREBASE_* at build time (public values, not secrets; see externals/E05).
// Without config the app runs in local dev mode against a backend with PC_AUTH_DISABLED=true.
import { initializeApp } from "firebase/app";
import {
  GoogleAuthProvider,
  getAuth,
  onAuthStateChanged,
  signInAnonymously,
  signInWithPopup,
  signOut as fbSignOut,
  type Auth,
  type User,
} from "firebase/auth";

const env = import.meta.env;
let auth: Auth | null = null;

// Sign in must finish on the same origin the app is served from. With authDomain on
// another host (aibuilderscup.firebaseapp.com while the page is proofcard.web.app) the
// auth iframe is a third party, browsers partition its storage, and the popup result
// never reaches the app: the popup closes and the user stays signed out. Every Firebase
// Hosting site serves /__/auth/handler itself, so on our hosting sites we use the page's
// own host. Each one needs its /__/auth/handler in the OAuth client's redirect URIs.
const HOSTED_AUTH_DOMAINS = new Set([
  "proofcard.web.app",
  "proofcard.firebaseapp.com",
  "aibuilderscup.web.app",
  "aibuilderscup.firebaseapp.com",
]);

function authDomain(): string | undefined {
  const host = typeof window !== "undefined" ? window.location.hostname : "";
  return HOSTED_AUTH_DOMAINS.has(host) ? host : env.VITE_FIREBASE_AUTH_DOMAIN;
}

if (env.VITE_FIREBASE_API_KEY) {
  const app = initializeApp({
    apiKey: env.VITE_FIREBASE_API_KEY,
    authDomain: authDomain(),
    projectId: env.VITE_FIREBASE_PROJECT_ID,
    appId: env.VITE_FIREBASE_APP_ID,
  });
  auth = getAuth(app);
}

export const devMode = auth === null;

export interface SignedIn {
  name: string;
  photo: string | null;
  isAnonymous?: boolean;
}

export function watchUser(cb: (u: SignedIn | null) => void): () => void {
  if (!auth) {
    cb({ name: "Local dev", photo: null });
    return () => {};
  }
  return onAuthStateChanged(auth, (u: User | null) =>
    cb(
      u
        ? {
            name: u.displayName ?? u.email ?? (u.isAnonymous ? "Guest" : "You"),
            photo: u.photoURL,
            isAnonymous: u.isAnonymous,
          }
        : null,
    ),
  );
}

export async function signIn(): Promise<void> {
  if (!auth) return;
  try {
    await signInWithPopup(auth, new GoogleAuthProvider());
  } catch (e) {
    const code = (e as { code?: string }).code ?? String(e);
    console.error("sign in failed:", code);
    if (code !== "auth/popup-closed-by-user" && code !== "auth/cancelled-popup-request") {
      window.alert(`Sign in failed (${code}). Please try again.`);
    }
  }
}

export async function signInGuest(): Promise<void> {
  if (auth) await signInAnonymously(auth);
}

export async function signOut(): Promise<void> {
  if (auth) await fbSignOut(auth);
}

export async function idToken(): Promise<string | null> {
  if (devMode) return "local-dev"; // backend runs with PC_AUTH_DISABLED=true locally
  return auth?.currentUser ? auth.currentUser.getIdToken() : null;
}
