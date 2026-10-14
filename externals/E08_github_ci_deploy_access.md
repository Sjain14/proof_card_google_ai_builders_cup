# E08 · GitHub: CI deploy access (keyless) + repo settings

**Deadline:** 15 Oct · **Needs:** E03, E06.

CI already runs lint, types, tests and rules tests on every PR. This step lets the `deploy` workflow push to Cloud Run on merge to `main` without any long lived key, using Workload Identity Federation ✅ [google-github-actions/auth](https://github.com/google-github-actions/auth#preferred-direct-workload-identity-federation), ✅ [WIF with deployment pipelines](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).

## Steps
```bash
P=$(gcloud config get-value project); PN=$(gcloud projects describe $P --format='value(projectNumber)')
REPO=Sjain14/proof_card_google_ai_builders_cup
gcloud iam service-accounts create deploy-sa --display-name="CI deployer"
gcloud iam workload-identity-pools create github --location=global
gcloud iam workload-identity-pools providers create-oidc repo --location=global \
  --workload-identity-pool=github --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository \
  --attribute-condition="assertion.repository=='$REPO'"
gcloud iam service-accounts add-iam-policy-binding deploy-sa@$P.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PN/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"
# What the workflows need: deploy.yml (image to Cloud Run, Hosting, Firestore rules + indexes)
# and bench.yml (Vertex calls). Images are built in GitHub Actions, so no Cloud Build role.
for ROLE in roles/run.admin roles/artifactregistry.writer roles/firebasehosting.admin \
            roles/firebaserules.admin roles/datastore.indexAdmin roles/aiplatform.user \
            roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $P --member="serviceAccount:deploy-sa@$P.iam.gserviceaccount.com" --role=$ROLE
done
# Act as the runtime service account on deploy (only that one, not project wide).
gcloud iam service-accounts add-iam-policy-binding api-sa@$P.iam.gserviceaccount.com \
  --member="serviceAccount:deploy-sa@$P.iam.gserviceaccount.com" --role=roles/iam.serviceAccountUser
# Image repository + APIs the Firebase CLI calls.
gcloud artifacts repositories create proofcard --repository-format=docker --location=asia-south1
gcloud services enable firebasehosting.googleapis.com firebaserules.googleapis.com
# Only if E16 is done and you want the benchmark to use published fact checks:
gcloud secrets add-iam-policy-binding factcheck-api-key \
  --member="serviceAccount:deploy-sa@$P.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor
```

Then in GitHub → repo → Settings → Secrets and variables → Actions → **Variables** (not secrets, none of these are sensitive):

| Variable | Value |
|---|---|
| `GCP_PROJECT` | your project id |
| `GCP_REGION` | `asia-south1` |
| `GCP_WIF_PROVIDER` | `projects/<PN>/locations/global/workloadIdentityPools/github/providers/repo` |
| `GCP_DEPLOY_SA` | `deploy-sa@<project>.iam.gserviceaccount.com` |
| `PROOF_BUCKET` | bucket from E04 |
| `FIREBASE_WEB_API_KEY` | `apiKey` from the E05 web config (public, not a secret ✅ [Firebase API keys](https://firebase.google.com/docs/projects/api-keys)) |
| `FIREBASE_WEB_APP_ID` | `appId` from the same config |

## What the workflows do
- `.github/workflows/deploy.yml`: after `ci` is green on a push to `main` (or by hand: Actions → deploy → Run workflow). Builds the API image, pushes to `asia-south1-docker.pkg.dev/<project>/proofcard/api:<sha>`, `gcloud run deploy --image` (keeps every env var, secret and the service account from E09), probes `/api/health`, builds the frontend with `VITE_LIVE_ORIGIN` = the Cloud Run URL, deploys Hosting + Firestore rules + indexes. Skips itself while `GCP_PROJECT` is empty; fails with a clear message if E09 (first manual deploy) hasn't happened.
- `.github/workflows/bench.yml`: by hand only (Actions → bench → Run workflow, tick "factcheck" after E16). Runs `python -m bench.run --mode vertex` as deploy-sa, in memory store, no writes to Firestore or the bucket. Result: table in the run summary + JSON artifact `bench-results`, which Agent commits under `backend/bench/results/` and feeds into `context/DECK_TEXT.md`.
- 🟡 The Firebase CLI does not read the WIF credentials file, so the deploy passes a short lived access token instead ([firebase-tools #10726](https://github.com/firebase/firebase-tools/issues/10726)). If the Hosting step says "Failed to authenticate", paste the log line to Agent.

Repo settings:
1. Branch protection on `main`: require PR + CI green ✅ [Protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches). Allow the agent account to merge (you said don't wait).
2. 🔴 Make the repo **public** before submission (Settings → General → Danger zone → Change visibility). Submission requires a public repo ✅ (your submission page file).

## Done when
Variables set; after E09, the `deploy` workflow run on `main` turns green and `bench` runs once by hand. Until then deploys are manual (E09).
