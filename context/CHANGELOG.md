# CHANGELOG

Every PR adds one entry on top: date (IST), PR link, what changed, which context docs it touched.

## 2026-10-14 · v0.5.6 · fix/public-snapshots
- `GET /api/snapshots/<sha256>` (audit #16): the exact stored bytes of any proof page, so anyone can run `sha256sum` and check the hash on a card. Always a download (`application/octet-stream`, attachment), never rendered on our origin; bytes re-hashed before serving; public rate limit; immutable cache. Share page links every page hash to it.
- No new dependencies, no Hosting change (`/api/**` rewrite already covers it). Docs touched: CHANGELOG.

## 2026-10-14 · v0.5.5 · fix/local-run-limits
- `/api/prebunk` limits (audit #14): per user burst (`PC_PREBUNK_PER_MIN`, default 3) + durable daily cap (`PC_PREBUNK_DAILY_CAP`, default 20) counted server side in Firestore (one aggregation read on the existing owner_uid + created_at index), so it holds across Cloud Run instances. Each brief is ~15 grounded calls on the bill.
- Local run fixed (audit #15): stub mode without `PC_GCP_PROJECT` uses the in memory store instead of crashing on missing Google credentials.
- No new dependencies. Docs touched: CHANGELOG.

## 2026-10-14 · v0.5.4 · fix/live-transcribe
- Every `input_transcription` is treated as a final segment, as the Live transcription docs define it; no wait on a `finished` flag that `gemini-3.5-transcribe-live` may never set (audit #11). Interim hypotheses are ignored.
- `custom_vocabulary` from the session's prebunked claims (names, acronyms, Indic words, ≤ 100 as the docs advise) biases recognition toward exactly the claims we hold cards for.
- No new dependencies. Docs touched: CHANGELOG.

## 2026-10-14 · v0.5.3 · fix/proof-match
- Hindi / Hinglish proof (audit #5): tokenizer keeps Indic combining marks (`संविधान` was split into 4 letters) and reads Devanagari digits; Hindi + Hinglish stopwords; RapidFuzz fuzzy token hits (ratio ≥ 85, words ≥ 4 chars) for inflections and transliteration variants.
- Cross-lingual: the assess call now also returns `CLAIM_EN` (same call, no extra cost); every source is matched on the claim as said, its English restatement and the model's supporting sentence. Prompt version 2026-10-14.2.
- Debunks survive the gate (audit #6): for FALSE / MISLEADING, an on topic passage that states a different number counts as support (it is the counter evidence). TRUE still needs the claim's own numbers.
- New dep (pinned): rapidfuzz 3.14.6 (MIT). Docs touched: CHANGELOG, skills.md, DECISIONS (D20).

## 2026-10-14 · v0.5.2 · fix/proof-fetch
- One slow or broken source no longer fails the whole claim: every `httpx.HTTPError` (timeout, DNS, TLS, proxy) becomes `FetchError` and that source is skipped (audit #7).
- Main content extraction with trafilatura (plan C2), hand parser kept only as fallback: no more menu / pager text as proof snippets (audit #10).
- PDF sources accepted (10 MB, first 60 pages, pypdf text layer): MoSPI / RBI / PIB figures are mostly PDFs (audit #13).
- `HttpFetcher` now tested on `httpx.MockTransport` (redirects, errors, size caps, SSRF, PDF); it was `pragma: no cover` before.
- New deps (pinned): trafilatura 2.3.1 (Apache-2.0), pypdf 6.20.1 (BSD-3-Clause). Docs touched: CHANGELOG, skills.md.

## 2026-10-14 · v0.5.1 · fix/models-regions
- Default model `gemini-3.5-flash` (GA, retires no sooner than May 2027) on the `global` endpoint; `gemini-2.5-flash` retires on Vertex 20 Oct 2026, the second day of scoring.
- Separate locations per model: `PC_LIVE_REGION` (default `global`, validated to global / us / eu, the only places `gemini-3.5-transcribe-live` exists), `PC_EMBED_REGION` (default = `PC_GCP_REGION`). Before, all three models used `asia-south1`, where live transcription is not served.
- Audit fixes #3, #4. No new dependencies. Docs touched: CHANGELOG, externals E10, backend/.env.example.

## 2026-10-14 · v0.5.0 · p5-live-bridge
- Live bridge: `WS /api/live/:id` (first message auth, owner only, Origin allowlist), Gemini Live transcription relay with reconnect, claim spotting (filter + model), instant match on embeddings vs prebunked cards, cold path through the same `verify_claim()`; live claims stored with `matched_claim_id` + `latency_ms`.
- Frontend `/s/:id/live`: YouTube player, tab audio capture (AudioWorklet, PCM16 16 kHz), typed line fallback, live feed with PREBUNKED / LIVE badges and latency chips; "Go live" on a ready brief.
- Fix: local dev mode now works end to end (`PC_AUTH_DISABLED` was never wired; dev token `local-dev`).
- Criteria: C1 third GenAI job (live semantic match) + live transcription; C3 the Before + During moment; C4 latency visible on every card.
- No new dependencies. Docs touched: ARCHITECTURE, DECISIONS (D17 to D19), SNAPSHOT, CHANGELOG, versions/v0.5.0, externals E09 + E10.

## 2026-10-14 · v0.4.1 · criteria-gate
- Judging gate: `context/judging-criteria.md` (official criteria + weights, road to Singapore dates, criterion to phase to demo moment, finalist bar), PR template with the criteria checklist.
- `context/ASSETS.md` (source + licence per asset), design system + motion timings in `05_UI_UX.md` §7.
- Rules tests deps bumped together (firebase 13, @firebase/rules-unit-testing 6, firebase-tools 15; peer coupled, so the three single bumps #2 to #4 could not pass alone); rules CI job on Node 24 (firebase 13 engine) + Java 21 (firebase-tools 15).
- Criteria: C1 gates hold quality on every phase; C4 design system written down. No feature change.
- Docs touched: judging-criteria, ASSETS, 05_UI_UX, SNAPSHOT, CHANGELOG, versions/v0.4.1, AGENTS.md.

## 2026-10-14 · v0.4.0 · p4-frontend
- Fix: landing example cards no longer overflow on mobile (390px).
- Frontend app (landing, new brief, brief grid with share actions), Firebase Google sign in, Hosting rewrites, CI frontend job.
- New deps (pinned): react, react-dom, firebase, @fontsource-variable/inter (OFL); dev: vite, @vitejs/plugin-react, typescript, vitest, @types/react(-dom).
- Docs touched: SNAPSHOT, CHANGELOG, ARCHITECTURE, DECISIONS (D16), versions/v0.4.0, skills.md.

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
