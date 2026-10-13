# E05 · Firebase: Hosting + Auth

**Deadline:** 14 Oct · **Needs:** E03 · **Unblocks:** frontend on a public URL, signed in brief creation.

## Steps
1. Firebase console → Add project → choose your existing GCP project ✅ [Add Firebase to a Google Cloud project](https://firebase.google.com/docs/projects/use-firebase-with-existing-cloud-project).
2. Build → Authentication → Get started → enable **Google** and **Anonymous** providers ✅ [Firebase Auth web](https://firebase.google.com/docs/auth/web/start). Add your Hosting domain + `localhost` to Authorized domains.
3. Project settings → Your apps → Add web app → copy the `firebaseConfig` object. This config is **not a secret** ✅ [Firebase docs: API keys for Firebase](https://firebase.google.com/docs/projects/api-keys), security comes from Auth + rules.
4. Put it in `frontend/.env.local` (gitignored) using the names in `frontend/.env.example`, or DM it; Agent can commit it as public config.
5. Install the CLI and link the repo ✅ [Firebase CLI](https://firebase.google.com/docs/cli):
   ```bash
   npm i -g firebase-tools
   firebase login
   firebase use --add   # pick your project, alias "prod"
   ```
   `firebase.json` is already in the repo (Hosting serves `frontend/dist`, `/api/**` and `/v/**` rewrite to Cloud Run). Don't re-run `firebase init hosting` over it.
6. Optional but recommended: App Check with reCAPTCHA Enterprise for the web app ✅ [App Check](https://firebase.google.com/docs/app-check/web/recaptcha-enterprise-provider). Agent wires the client side behind a flag.

## Done when
`firebase projects:list` shows the project, Google + Anonymous sign in enabled, web config shared.
