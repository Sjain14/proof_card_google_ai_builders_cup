# ARCHITECTURE (living)

The full design is in `03_Architecture_Integrations_APIs.md`; standards in `12_Engineering_Standards.md`. This file tracks what EXISTS in code right now, so it stays short and true.

## Planned repo layout
```
backend/            Python FastAPI service for Cloud Run (Agent)
  app/              main, auth, config, schemas, security, store, logging_setup, asgi
  tests/            pytest
frontend/           Vite + React + TS (Team lead)
rules-tests/        Firestore rules tests on the emulator
firestore.rules, firestore.indexes.json, firebase.json
.github/workflows/  CI
context/            these docs
```

## Built so far
| Piece | State |
|---|---|
| Main service skeleton (`/healthz`, `/api/prebunk`, `/api/cards/:id`, `/api/check`, `/tg/webhook`) | in PR p1-backend-skeleton |
| Auth (Firebase ID tokens, admin vs anonymous) | in PR p1-backend-skeleton |
| Firestore schema v1 (sessions, claims, cards, server only collections) + rules | in PR p1-backend-skeleton |
| Gemini pipeline, Cloud Tasks, fetcher service, card PNG, Telegram replies | not started (P1 to P4) |

## Data flow (target)
Admin browser → Firebase Hosting → Cloud Run main (auth) → Cloud Tasks `verify_claim` → fetcher (zero role SA) → Gemini on Vertex + Search grounding + check grounding → Firestore + Cloud Storage → browser listener / `/v/:id` / Telegram bot.
