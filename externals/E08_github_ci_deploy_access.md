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
for ROLE in roles/run.admin roles/artifactregistry.writer roles/cloudbuild.builds.editor roles/iam.serviceAccountUser roles/firebasehosting.admin; do
  gcloud projects add-iam-policy-binding $P --member="serviceAccount:deploy-sa@$P.iam.gserviceaccount.com" --role=$ROLE
done
```

Then in GitHub → repo → Settings → Secrets and variables → Actions → **Variables** (not secrets, none of these are sensitive):

| Variable | Value |
|---|---|
| `GCP_PROJECT` | your project id |
| `GCP_REGION` | `asia-south1` |
| `GCP_WIF_PROVIDER` | `projects/<PN>/locations/global/workloadIdentityPools/github/providers/repo` |
| `GCP_DEPLOY_SA` | `deploy-sa@<project>.iam.gserviceaccount.com` |
| `PROOF_BUCKET` | bucket from E04 |

Repo settings:
1. Branch protection on `main`: require PR + CI green ✅ [Protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches). Allow the agent account to merge (you said don't wait).
2. 🔴 Make the repo **public** before submission (Settings → General → Danger zone → Change visibility). Submission requires a public repo ✅ (your submission page file).

## Done when
Variables set; the `deploy` workflow run on `main` turns green. Until then deploys are manual (E09).
