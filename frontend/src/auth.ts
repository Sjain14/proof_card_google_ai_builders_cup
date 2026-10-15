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

if (env.VITE_FIREBASE_API_KEY) {
  const app = initializeApp({
    apiKey: env.VITE_FIREBASE_API_KEY,
    authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
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
  if (auth) await signInWithPopup(auth, new GoogleAuthProvider());
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
