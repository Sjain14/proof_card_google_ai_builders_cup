# E06 · Service accounts, least privilege

**Deadline:** 14 Oct · **Needs:** E03, E04.

Two runtime identities, no JSON keys ever downloaded ✅ [Best practices for service accounts](https://cloud.google.com/iam/docs/best-practices-service-accounts).

## Steps
```bash
P=$(gcloud config get-value project)
gcloud iam service-accounts create api-sa --display-name="Proof Card API"
gcloud iam service-accounts create bot-sa --display-name="Proof Card Telegram bot"

for ROLE in roles/aiplatform.user roles/datastore.user roles/storage.objectAdmin \
            roles/cloudtasks.enqueuer roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding $P \
    --member="serviceAccount:api-sa@$P.iam.gserviceaccount.com" --role=$ROLE
done

for ROLE in roles/datastore.user roles/secretmanager.secretAccessor roles/storage.objectViewer; do
  gcloud projects add-iam-policy-binding $P \
    --member="serviceAccount:bot-sa@$P.iam.gserviceaccount.com" --role=$ROLE
done
```
Roles reference ✅ [IAM basic and predefined roles](https://cloud.google.com/iam/docs/understanding-roles).

🟡 Tighter option if time allows: grant `secretAccessor` per secret instead of project wide (`gcloud secrets add-iam-policy-binding`).

## Done when
`gcloud iam service-accounts list` shows `api-sa` and `bot-sa`. Nothing to hand over.
