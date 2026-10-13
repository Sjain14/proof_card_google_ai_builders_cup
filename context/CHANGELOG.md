# CHANGELOG

Every PR adds one entry on top: date (IST), PR link, what changed, which context docs it touched.

## 2026-10-14 · v0.1.0 · PR #1 p1-backend-skeleton
- `backend/`: FastAPI service skeleton, Firebase ID token auth (admin vs anonymous), Pydantic schemas for every request + Firestore doc (schema v1), verdict faithfulness gate, Telegram webhook secret check, SSRF guard, rate limiter, JSON logging with redaction, non root Dockerfile.
- `firestore.rules` (deny by default, owner only sessions, public card get without list) + `rules-tests/` (6 emulator tests), `firestore.indexes.json`, `firebase.json`.
- CI: ruff, format, mypy strict, pytest (85% floor, now 97%), pip-audit, rules tests; actions pinned to SHAs; Dependabot.
- Docs touched: SNAPSHOT, CHANGELOG, ARCHITECTURE.

## 2026-10-14 · v0.0.2 · direct to main (docs only)
- Added `externals/` (E01 to E14): every human setup step, phase by phase, with done-when lines.
- Added `context/versions/` (one md per version). CONVENTIONS: no wait PR flow.

## 2026-10-14 · v0.0.1 · direct to main (docs only, agreed in DM)
- Added `context/` with docs 00 to 12 (PRD, stack, architecture, flows, UI/UX, brand proposal, features, reuse map, dev plan, criteria map, setup list, engineering standards).
- Added dev memory docs: SNAPSHOT, CHANGELOG, ARCHITECTURE, DECISIONS, CONVENTIONS.
