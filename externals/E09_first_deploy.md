# E09 · First deploy (manual, once) + Telegram webhook

**Deadline:** 15 Oct · **Needs:** E03 to E07. After E08 works, CI does this on every merge.

## 1. Backend to Cloud Run
✅ [Deploy from source](https://cloud.google.com/run/docs/deploying-source-code) · ✅ [Secrets as env vars](https://cloud.google.com/run/docs/configuring/services/secrets)
```bash
P=$(gcloud config get-value project); R=asia-south1
cd backend
gcloud run deploy proofcard-api --source . --region $R \
  --service-account api-sa@$P.iam.gserviceaccount.com \
  --allow-unauthenticated --min-instances 1 --max-instances 5 --timeout 3600 \
  --set-env-vars PC_ENV=prod,PC_GCP_PROJECT=$P,PC_GCP_REGION=$R,PC_MODEL_MODE=vertex,PC_PROOF_BUCKET=$P-proofs,PC_TASKS_MODE=cloudtasks,PC_TELEGRAM_BOT_USERNAME=<your_bot_username_without_@>,PC_TASKS_SA_EMAIL=api-sa@$P.iam.gserviceaccount.com \
  --set-secrets PC_TELEGRAM_BOT_TOKEN=TG_BOT_TOKEN:1,PC_TELEGRAM_WEBHOOK_SECRET=TG_WEBHOOK_SECRET:1
```
Secrets are pinned to version `1`, not `latest` (see `context/12_Engineering_Standards.md`). `--allow-unauthenticated` is required because the share link and Telegram webhook are public; every write endpoint checks a Firebase ID token itself.

After it prints the service URL, set it as the task audience and the public base:
```bash
URL=$(gcloud run services describe proofcard-api --region $R --format='value(status.url)')
gcloud run services update proofcard-api --region $R \
  --update-env-vars "^@^PC_SERVICE_URL=$URL@PC_PUBLIC_BASE_URL=https://<your-hosting-domain>@PC_LIVE_ORIGINS=https://$P.web.app,https://$P.firebaseapp.com"
```
`^@^` switches gcloud's list separator to `@`, because `PC_LIVE_ORIGINS` itself contains a comma ✅ [gcloud topic escaping](https://cloud.google.com/sdk/gcloud/reference/topic/escaping). Lock `PC_PUBLIC_BASE_URL` and `PC_TELEGRAM_BOT_USERNAME` before the first real card: both are printed on the card (QR + "forward to @bot" line), so changing them later makes older forwarded cards read ALTERED.

`--timeout 3600` lets one live session run up to an hour (the socket ends at the request timeout ✅ [Cloud Run websockets](https://cloud.google.com/run/docs/triggering/websockets)). For the frontend build, also set `VITE_LIVE_ORIGIN=$URL` next to the `VITE_FIREBASE_*` values: the live socket connects to Cloud Run directly because Hosting rewrites stop at 60 s (DECISIONS D17).

Create the job queue once (Cloud Tasks retries failed briefs with backoff) ✅ [Create queues](https://cloud.google.com/tasks/docs/creating-queues):
```bash
gcloud tasks queues create prebunk --location=$R --max-concurrent-dispatches=4 --max-attempts=3
gcloud iam service-accounts add-iam-policy-binding api-sa@$P.iam.gserviceaccount.com \
  --member=serviceAccount:api-sa@$P.iam.gserviceaccount.com --role=roles/iam.serviceAccountUser
PN=$(gcloud projects describe $P --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding api-sa@$P.iam.gserviceaccount.com \
  --member=serviceAccount:service-$PN@gcp-sa-cloudtasks.iam.gserviceaccount.com --role=roles/iam.serviceAccountUser
```
(the first binding lets the API attach api-sa to the tasks it creates; the second lets the Cloud Tasks service agent mint the OIDC token as api-sa when it calls us back ✅ [HTTP target tasks](https://cloud.google.com/tasks/docs/creating-http-target-tasks), "grant the Service Account User role to the Cloud Tasks primary service agent").

## 2. Frontend + rules to Firebase
```bash
cd ../frontend && npm ci && npm run build && cd ..
firebase deploy --only hosting,firestore:rules,firestore:indexes
```
`firebase.json` rewrites `/api/**` and `/v/**` to `proofcard-api` ✅ [Hosting + Cloud Run](https://firebase.google.com/docs/hosting/cloud-run).

## 3. Point Telegram at the backend
✅ [setWebhook](https://core.telegram.org/bots/api#setwebhook). Run on your machine, values pulled from Secret Manager so nothing is typed:
```bash
TOKEN=$(gcloud secrets versions access 1 --secret=TG_BOT_TOKEN)
SECRET=$(gcloud secrets versions access 1 --secret=TG_WEBHOOK_SECRET)
curl -s "https://api.telegram.org/bot$TOKEN/setWebhook" \
  -d url="https://<your-hosting-domain>/tg/webhook" -d secret_token="$SECRET" \
  -d allowed_updates='["message","inline_query","callback_query"]'
unset TOKEN SECRET
```
Expect `{"ok":true,...}`.

## 4. Smoke test
1. `https://<domain>/` loads the homepage.
2. `https://<domain>/api/health` → `{"status":"ok"}`.
3. Sign in, create a brief on the sample topic, cards appear.
4. Open a card, tap "Share to Telegram", forward it to the bot → VERIFIED.

## Done when
All 4 smoke checks pass. DM the hosting URL.
