# E04 · Enable the Google APIs

**Deadline:** 14 Oct · **Needs:** E03.

## Steps
One command ✅ [gcloud services enable](https://cloud.google.com/sdk/gcloud/reference/services/enable):

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  cloudtasks.googleapis.com \
  iamcredentials.googleapis.com \
  factchecktools.googleapis.com \
  speech.googleapis.com \
  firebase.googleapis.com \
  identitytoolkit.googleapis.com
```

Then create the Firestore database in Native mode, same region as E03 ✅ [Create a Firestore database](https://cloud.google.com/firestore/docs/create-database-server-client-library):

```bash
gcloud firestore databases create --location=asia-south1 --type=firestore-native
```

And a Cloud Storage bucket for proof snapshots and card PNGs (uniform access, not public) ✅ [Create buckets](https://cloud.google.com/storage/docs/creating-buckets):

```bash
P=$(gcloud config get-value project)
gcloud storage buckets create gs://$P-proofs --location=asia-south1 --uniform-bucket-level-access
```

🟡 If any API name above errors, search it in Console → APIs & Services → Library and enable from there.

## Done when
`gcloud services list --enabled` shows all of them, Firestore and the bucket exist. DM the bucket name (`<project-id>-proofs`, same name in E08 and E09).
