# E15 · Firestore to BigQuery export (analytics + benchmark)

**Deadline:** 17 Oct · **Needs:** E03 to E05 · **Unblocks:** the measured numbers on the deck (prebunk hit rate, latency, ALTERED catch rate) and the BigQuery line in the stack.

## Steps
1. Enable BigQuery: `gcloud services enable bigquery.googleapis.com`.
2. Run `sql/01_create_dataset.sql` (see `sql/README.md` for the one line loop).
3. Install the official extension three times, once per collection ✅ [Stream Firestore to BigQuery](https://extensions.dev/extensions/firebase/firestore-bigquery-export):
   ```bash
   firebase ext:install firebase/firestore-bigquery-export --project=<your-project>
   ```
   | Instance | Collection path | Dataset | Table id |
   |---|---|---|---|
   | `bq-cards` | `cards` | `proofcard_raw` | `cards` |
   | `bq-claims` | `sessions/{sessionId}/claims` | `proofcard_raw` | `claims` |
   | `bq-checks` | `checks` | `proofcard_raw` | `checks` |
   Location `asia-south1`, same as the dataset.
4. Run the rest of `sql/` (02 to 05).
5. Create one brief in the app, wait a minute, then in BigQuery run
   `SELECT * FROM proofcard_analytics.m_verdict_mix` and check rows appear.

🟡 Note: the extension only streams new writes. Docs created before step 3 need the extension's backfill script (in its docs) or simply create fresh demo data after install.

## Done when
`m_verdict_mix` returns rows. DM "bq live".
