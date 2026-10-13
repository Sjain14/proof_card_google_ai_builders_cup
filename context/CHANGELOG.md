# CHANGELOG

Every PR adds one entry on top: date (IST), PR link, what changed, which context docs it touched.

## 2026-10-14 · v0.3.0 · p3-proof-capsule
- Card image + QR, ALTERED check, `/v/:id` share page, image + text checks, Telegram bot replies + inline share, `checks` logging.
- AGENTS.md + context/skills.md (Team lead: official docs first, no bloat). Fonts subset.
- New deps (pinned): pillow, numpy, ImageHash, zxing-cpp, python-multipart.
- Docs touched: SNAPSHOT, CHANGELOG, ARCHITECTURE, DECISIONS (D14, D15), versions/v0.3.0, E09.

## 2026-10-14 · v0.2.0 · PR #5 p2-prebunk-pipeline
- Prebunk pipeline: Gemini prediction + grounded assessment, own fetch + passage match + sha256 snapshots, faithfulness gate, Cloud Tasks job with OIDC, owner only session view, offline stub mode.
- `sql/` BigQuery views + metrics; `externals/E15`; E09 gets queue + task env.
- Schema v1 additive fields on claims: verdict, matched_claim_id, latency_ms.
- Docs touched: SNAPSHOT, CHANGELOG, ARCHITECTURE, DECISIONS (D9 to D13), versions/v0.2.0.

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
