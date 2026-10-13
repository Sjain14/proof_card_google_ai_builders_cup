# ARCHITECTURE (living)

The full design is in `03_Architecture_Integrations_APIs.md`; standards in `12_Engineering_Standards.md`. This file tracks what EXISTS in code right now, so it stays short and true.

## Repo layout
```
backend/            Python FastAPI service for Cloud Run
  app/
    main.py         routes + wiring (create_app with injectable deps)
    auth.py         Firebase ID token verification (admin vs anonymous)
    config.py       settings from env / Secret Manager (PC_*)
    schemas.py      Pydantic boundary + Firestore doc models (schema v1)
    store.py        Store protocol: InMemory + Firestore, revalidating updates
    model.py        ModelClient: StubModel (offline) + VertexModel (Gemini + Search grounding)
    proof.py        fetch (SSRF guarded), text extract, passage match, sha256 snapshots (GCS)
    pipeline.py     run_prebunk / verify_claim / build_card
    tasks.py        InlineQueue (local) + CloudTasksQueue (prod) + OIDC verifier
    fixtures.py     offline demo facts
    security.py     webhook secret, SSRF guard, canonical hashing, rate limit
  tests/            pytest (unit + API)
frontend/           (P4) Vite + React + TS
rules-tests/        Firestore rules tests on the emulator
sql/                BigQuery views + metrics (NN_name.sql)
externals/          human setup tasks E01..E15
context/            docs, dev memory, versions/
```

## Endpoints
| Route | Auth | What |
|---|---|---|
| `GET /healthz` | none | liveness |
| `POST /api/prebunk` | Firebase user (not anonymous) | create session, enqueue prebunk job |
| `GET /api/sessions/:id` | owner only (404 otherwise) | session + claims + counts |
| `GET /api/cards/:id` | public | one immutable card |
| `POST /api/check` | public, rate limited | text compare (P3 upgrades to full ALTERED) |
| `POST /tasks/prebunk` | Google OIDC for api-sa only | run the prebunk job |
| `POST /tg/webhook` | Telegram secret_token header | bot updates (P3 replies) |

## Data flow (built)
```
browser ─POST /api/prebunk─▶ main (auth) ─▶ Firestore sessions/{sid}
                                   └─enqueue─▶ Cloud Tasks ─OIDC─▶ /tasks/prebunk
run_prebunk: Gemini predict N claims ─▶ claims/{cid} queued
  for each claim (4 parallel): Gemini + Google Search grounding ─▶ evidence URLs
    ─▶ our fetch (SSRF check every hop) ─▶ passage match ─▶ sha256 ─▶ GCS snapshots/<sha>
    ─▶ gate_verdict ─▶ cards/{id} (create only) ─▶ claim proved + verdict
browser reads session via /api/sessions/:id (or Firestore listener, rules owner only)
```

## Not built yet
Card PNG + QR, ALTERED (text diff + pHash), Telegram replies + inline share (P3) · frontend (P4) · live bridge + instant match (P5).
