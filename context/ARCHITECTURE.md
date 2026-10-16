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
    card_image.py   deterministic 1080x1350 card + QR (zxing-cpp), Noto fonts (OFL)
    alter.py        ALTERED check: QR id, re-render, per band tile diff, pHash
    share_page.py   server rendered /v/:id
    telegram.py     Bot API subset + update handler
    security.py     webhook secret, SSRF guard, canonical hashing, rate limit
  tests/            pytest (unit + API)
frontend/           Vite + React + TS (no router/UI lib): Landing, New brief, Brief grid
  src/              api.ts (typed client), auth.ts (Firebase Google sign in), router.ts, pages/, components/
rules-tests/        Firestore rules tests on the emulator
sql/                BigQuery views + metrics (NN_name.sql)
externals/          human setup tasks E01..E15
context/            docs, dev memory, versions/
```

## Endpoints
| Route | Auth | What |
|---|---|---|
| `GET /api/health` (+ `/healthz` local) | none | liveness; probe `/api/health` on Cloud Run (paths ending in z are reserved there) |
| `POST /api/prebunk` | Firebase user (not anonymous) | create session, enqueue prebunk job |
| `GET /api/sessions/:id` | owner only (404 otherwise) | session + claims + counts |
| `GET /api/sessions/:id/facts` | owner only (404 otherwise) | the session's research fact bank as JSON |
| `GET /api/cards/:id` | public | one immutable card |
| `POST /api/check` | public, rate limited | text compare with word diff |
| `POST /tasks/prebunk` | Google OIDC for api-sa only | run the prebunk job |
| `POST /api/check/image` | public, rate limited, 10 MB | ALTERED check of a card image |
| `GET /v/:id` · `/v/:id.png` · `/v/:id.jpg` | public | share page (OG tags, proof, check form) + card image |
| `POST /v/:id/check` | public, rate limited | upload a forwarded copy, page shows VERIFIED / ALTERED |
| `POST /tg/webhook` | Telegram secret_token header | photo check, card lookup, inline share |
| `WS /api/live/:id` | first message `{"type":"auth","token"}`, owner only, Origin allowlist in prod (one close code 4401 for every auth failure, 4403 bad Origin) | tab audio (PCM16 16 kHz binary) or typed lines in; `ready` / `heard` / `match` / `checking` / `proved` / `failed` / `skipped{reason: not_checkable, repeat, error}` / `error` events out; every `heard` ends in `match`, `checking`, or `skipped` |

## Data flow (built)
```
browser ─POST /api/prebunk─▶ main (auth) ─▶ Firestore sessions/{sid}
                                   └─enqueue─▶ Cloud Tasks ─OIDC─▶ /tasks/prebunk
run_prebunk: fact bank (app/facts.py) ─▶ fact_banks/{topic+speaker}: reuse if < 7 days, else
  10 angles ─▶ 10 grounded Gemini calls ─▶ ~120 facts ─▶ fetch each source, keep if passage + figure match
run_prebunk: Gemini predict N claims ─▶ claims/{cid} queued
  for each claim (4 parallel): fact bank ruling first (judge picks deciding facts ─▶ their pages)
    else Gemini + Google Search grounding ─▶ evidence URLs
    ─▶ our fetch (SSRF check every hop) ─▶ passage match ─▶ sha256 ─▶ GCS snapshots/<sha>
    ─▶ gate_verdict ─▶ cards/{id} (create only) ─▶ claim proved + verdict
browser reads session via /api/sessions/:id (or Firestore listener, rules owner only)

LIVE (P5): browser tab audio ─getDisplayMedia─▶ AudioWorklet 16 kHz PCM16, 100 ms frames
  ─WS direct to Cloud Run (Hosting rewrites cap requests at 60 s)─▶ /api/live/:id
  ─▶ Gemini Live API transcription (auto language, Hinglish ok, reconnect at the 10 min cap)
  ─▶ final sentence ─▶ claim spotting (number / superlative pre filter, then Gemini JSON)
  ─▶ gemini-embedding-001 (SEMANTIC_SIMILARITY, 768) ─▶ cosine vs this session's proved
     prebunked claims ─▶ ≥ 0.80: push the existing card at once (PREBUNKED, latency in ms)
                     └▶ miss: claim LIVE `checking` ─▶ verify_claim() (same path as Before) ─▶ `proved`
```

## Deploy (v0.7.3)
`ci` green on main ─▶ `deploy.yml` (WIF as deploy-sa) ─▶ docker build ─▶ Artifact Registry `proofcard/api:<sha>` ─▶ `gcloud run deploy --image` ─▶ `/api/health` ─▶ frontend build (`VITE_LIVE_ORIGIN` = run URL) ─▶ Firebase Hosting + Firestore rules/indexes. First deploy by hand (E09). `bench.yml` by hand: vertex benchmark, JSON artifact.

## Not built yet
Clip upload fallback (B2) · Firestore onSnapshot instead of polling · benchmark runner (H2).
