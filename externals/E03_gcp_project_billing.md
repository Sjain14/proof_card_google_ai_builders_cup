# E03 · GCP project + billing + budget alert

**Deadline:** 14 Oct · **Unblocks:** every deploy.

## Steps
1. If the Cup gave you credits / a project, use that one. Otherwise create a new project ✅ [Create a project](https://cloud.google.com/resource-manager/docs/creating-managing-projects):
   ```bash
   gcloud projects create proofcard-<yourname> --name="Proof Card"
   gcloud config set project proofcard-<yourname>
   ```
2. Link billing ✅ [Enable billing](https://cloud.google.com/billing/docs/how-to/modify-project):
   Console → Billing → Link a billing account.
3. Budget alert at a small amount (for example ₹2,000) with email alerts at 50 / 90 / 100% ✅ [Create a budget](https://cloud.google.com/billing/docs/how-to/budgets).
4. Pick ONE region and use it everywhere: `asia-south1` (Mumbai). Before locking it, confirm the Gemini model you want is offered there (E10). If not, use `us-central1` for Vertex calls only.
5. Note the **project id** (not the name).

## What to hand Agent
Project id + region, in DM. These are not secrets.

## Done when
`gcloud config get-value project` prints your id and the budget alert email arrived.
