# CHANGELOG

Every PR adds one entry on top: date (IST), PR link, what changed, which context docs it touched.

## 2026-10-14 · v0.7.5 · p6-gemini-review-fixes
- Review of Team lead's Gemini audit: kept the real findings, dropped the rest. `PC_PROOF_BUCKET` now accepts `gs://name` or `name` (validator in `config.py`, `tests/test_config.py`).
- E09: Cloud Tasks service agent gets Service Account User on api-sa (docs require it for OIDC tasks); `--update-env-vars` uses `^@^` because `PC_LIVE_ORIGINS` contains a comma (old line failed to parse); lock base URL + bot username before the first card (both are printed on it, a later change reads ALTERED).
- E02: removed the false "one config line" rename claim (no `brand.ts` / `PC_BRAND_NAME`).
- Docs touched: E02, E09, SNAPSHOT, versions/v0.7.5, CHANGELOG.

## 2026-10-14 · v0.7.4 · p6-demo-inputs
- `externals/inputs/demo_claims.md` (E02 step 4: lock table, 5+ timed claims, one cold claim, Agent dry run section) and `externals/inputs/e11_results.md` (5 VERIFIED + 5 ALTERED runs, inline share, pass count quoted on slide 12).
- `context/demo/VO_SCRIPT.md`: 23 cues, 2:57, Hinglish VO + English caption + screen per cue, timed to the E12 beats, pace column, placeholders filled only from real runs. `context/demo/captions_en.srt`: same cues and times, ready for YouTube upload.
- Docs touched: E02, E11, E12 (pointers), SNAPSHOT, versions/v0.7.4, CHANGELOG.

## 2026-10-14 · v0.7.3 · p6-deploy-wif
- `.github/workflows/deploy.yml`: after green CI on main (or by hand), keyless via WIF: image built in Actions, pushed to Artifact Registry, `gcloud run deploy --image` (keeps E09 config), `/api/health` probe, frontend built with `VITE_LIVE_ORIGIN` = Cloud Run URL, Hosting + Firestore rules + indexes. No-op until `GCP_PROJECT` is set; refuses if E09 hasn't created the service.
- `.github/workflows/bench.yml`: manual `bench.run --mode vertex`, optional Fact Check key from Secret Manager (masked), report in the run summary + JSON artifact.
- `GET /api/health`: Cloud Run reserves some paths ending in "z" (`/healthz` may never reach us) and Hosting only rewrites `/api/**`. E09 smoke test pointed at a route that didn't exist (`/api/healthz`), fixed.
- Docs touched: E08 (roles, Artifact Registry repo, web config variables, what the workflows do), E09, ARCHITECTURE, SNAPSHOT, versions/v0.7.3, CHANGELOG.

## 2026-10-14 · v0.7.2 · p6-submission-draft
- `context/SUBMISSION_DRAFT.md`: submission description rewritten to match the real build (934 chars), claim to code table, swaps for submit day, "never claim" list (isolated fetcher, App Check, vector search, check grounding, EmbeddingGemma are not in code).
- `context/DECK_TEXT.md`: slide text for every template slide, criteria tags, as built architecture, benchmark placeholders keyed to the vertex result file.
- Docs touched: SUBMISSION_DRAFT (new), DECK_TEXT (new), 10_Criteria_Map, 02_Tech_Stack, 03_Architecture, SNAPSHOT, versions/v0.7.2, CHANGELOG.

## 2026-10-14 · v0.7.1 · feat/hindi-ui
- Hindi UI (audit #17): every screen string in `frontend/src/i18n.ts` (en + hi, Hindi typed against the English keys so a missing string fails `tsc`). Toggle in the nav (हिंदी / English), saved in localStorage, default from the browser language. `<html lang>` follows. Verdict words are the same as the card image and share page.
- Card content (claim, explanation, sources) stays in the language it was checked in. No new dependencies. Docs touched: CHANGELOG.

## 2026-10-14 · v0.7.0 · feat/clip-upload
- Clip upload fallback (plan B2, audit #12): `POST /api/sessions/:id/clip` (owner only, audio up to 20 MB / 15 min). One `gemini-3.5-transcribe` call (synchronous file transcription, custom vocabulary from the prebunked claims), then every sentence goes through the same `LiveEngine.on_sentence` as tab audio: instant prebunked match or cold path. Returns the events the socket would have pushed; the Live page replays them into the feed.
- Upload goes straight to Cloud Run (`VITE_LIVE_ORIGIN`, like the socket) because a long clip outlasts the Hosting rewrite timeout; CORS only for our own configured origins, POST + Authorization, no credentials.
- `PC_CLIP_MODEL` (default gemini-3.5-transcribe, served from `PC_LIVE_REGION`). No new dependencies. Docs touched: CHANGELOG.

## 2026-10-14 · v0.6.3 · feat/search-suggestions
- Grounding with Google Search display rules: the assess call's `search_entry_point.rendered_content` is kept on the card (`search_suggestion_html`, outside the proof fingerprint) and shown, unmodified, next to the grounded explanation on `/v/:id` and on every brief tile. Served as its own document (`/api/cards/:id/search-suggestion`, no scripts, own CSP, frame-ancestors self) inside a sandboxed iframe; a tap opens the Google results page directly (popup escapes sandbox).
- NOTICES gap closed. No new dependencies. Docs touched: CHANGELOG, NOTICES.

## 2026-10-14 · v0.6.2 · docs/readme-notices
- README: how it works, stack, local run without GCP, benchmark, credits (audit §5). NOTICES.md: every backend / frontend dependency with its licence (read from package metadata), fonts (OFL), Google services, benchmark data sources, langextract considered and not used (dependency weight).
- Flagged: Search grounding suggestions are not rendered on cards yet (grounding terms).
- Docs only. Docs touched: README, NOTICES, CHANGELOG.

## 2026-10-14 · v0.6.1 · feat/benchmark
- H1 gold set (`backend/bench/h1_gold.jsonl`): 50 source linked claims, en / hi / hi-Latn, TRUE + FALSE, 16 spoken paraphrases, 10 chit chat negatives (audit #8). Draft labels, Team lead reviews.
- H2 runner (`python -m bench.run --mode vertex --out ...`): accuracy, proof rate, UNVERIFIABLE rate, cold latency p50 / p95 per language; live instant match rate + chit chat false matches; ALTERED check on recompressed and edited cards. Prod wiring, in memory store.
- First stub run: tamper 150/150 VERIFIED clean, 150/150 edits caught (real code); accuracy needs the vertex run.
- No new dependencies. Docs touched: CHANGELOG, bench/README.

## 2026-10-14 · v0.6.0 · feat/factcheck-api
- Google Fact Check Tools API (plan A3, audit #17), behind `PC_FACTCHECK_API_KEY` (empty = off): published ClaimReviews (BOOM, Alt News, PIB Fact Check ...) become the first evidence, then grounding. They pass the same fetch, match, snapshot and gate as every source; the verdict stays with the model. Key sent as `X-Goog-Api-Key` header, never in a URL. Any API failure = no prior checks, never a failed claim.
- `ModelClient` wrapper (`app/factcheck.py`), pipeline untouched. Human step: externals E16.
- No new dependencies. Docs touched: CHANGELOG, externals E16 + README, backend/.env.example.

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
