# E16 · Fact Check Tools API key (optional, turns on prior fact checks)

**Deadline:** 16 Oct · **Needs:** E03, E07 (Secret Manager in use). **Time:** 10 min.

Why: with this key, every claim first asks Google's Fact Check Tools API whether BOOM, Alt News, PIB Fact Check, AFP etc. already reviewed it; those articles become the first sources on the card. Without the key the feature is simply off.

## Steps
1. APIs & Services → Library → enable **Fact Check Tools API** ✅ [docs](https://developers.google.com/fact-check/tools/api).
2. APIs & Services → Credentials → Create credentials → API key. Edit it: **API restrictions** → Restrict key → only "Fact Check Tools API". No application restriction is needed (server side only, never in the browser).
3. Store it, never paste it in chat:
   ```bash
   printf '%s' 'PASTE_KEY_HERE' | gcloud secrets create factcheck-api-key --data-file=-
   gcloud secrets add-iam-policy-binding factcheck-api-key \
     --member "serviceAccount:api-sa@$(gcloud config get-value project).iam.gserviceaccount.com" \
     --role roles/secretmanager.secretAccessor
   ```
4. On the next deploy add `--update-secrets PC_FACTCHECK_API_KEY=factcheck-api-key:1` (pinned version, like the Telegram secrets in E09).

## Done when
One DM line: "E16 done, secret version 1". Then Agent checks a known debunked claim shows the fact checker's article as the first source.
