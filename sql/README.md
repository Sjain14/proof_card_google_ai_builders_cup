# sql/ · BigQuery analytics

Hard truth first: the app database is **Firestore** (document store). It has no SQL, so there are no SQL migrations for it; its schema lives in `backend/app/schemas.py` (Pydantic, `schema_version` on every doc) and access in `firestore.rules`.

SQL here is for **BigQuery**: analytics, the honest benchmark numbers for the deck, and judge facing stats. Firestore streams into BigQuery with the official extension, then these files build typed views and metrics on top.

- Extension: Stream Firestore to BigQuery ✅ [extensions.dev](https://extensions.dev/extensions/firebase/firestore-bigquery-export). It writes `<table>_raw_changelog` and a `<table>_raw_latest` view with the document as a JSON string in `data` 🟡 (column names per the extension docs; check after install).
- Setup steps for the extension: `externals/E15_bigquery_export.md`.

## Run order

Files run in number order, each is idempotent (`CREATE ... IF NOT EXISTS` / `CREATE OR REPLACE VIEW`).

```bash
for f in sql/[0-9]*.sql; do
  sed "s/{{PROJECT}}/$(gcloud config get-value project)/g" "$f" | bq query --use_legacy_sql=false
done
```

| File | What |
|---|---|
| `01_create_dataset.sql` | `proofcard_analytics` dataset in `asia-south1` |
| `02_cards_view.sql` | typed view over exported cards |
| `03_claims_view.sql` | typed view over exported claims (all sessions) |
| `04_checks_view.sql` | typed view over Telegram / web ALTERED checks |
| `05_metrics_views.sql` | verdict mix, prebunk hit rate, ALTERED catch rate, latency |

Naming: `NN_name.sql`, never edit a shipped file's meaning; add a new number instead.
