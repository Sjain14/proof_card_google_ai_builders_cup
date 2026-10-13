# DECISIONS (ADR style)

One entry per decision: context, decision, why, consequence. Never edit an old entry; supersede it with a new one.

## D1 · 13 Oct · Scope narrowed
Live fact checking alone is common (InTruth, alandaitch/live-fact-checker, Devpost entries). Decision: Before (Prebunk Brief) + After (Proof Capsule) are the hero, live is a thin bridge from a pasted YouTube link. Pravachan Mode, extension, caption scraping, MCP, A2UI cut. Source: verdict doc + 07.

## D2 · 13 Oct · Telegram instead of WhatsApp
Telegram Bot API is free, supports deep links, inline share and buttons. Tradeoff: smaller India reach. Team lead's call.

## D3 · 13 Oct · No code from InTruth
Custom non commercial licence + Cup fresh project rule. Learn the approach only. Credit as inspiration in README.

## D4 · 13 Oct · Split
Agent: backend, Gemini pipeline, prebunk, Telegram bot, DB schema, security, docs. Team lead + team: frontend, GCP + deploy, video, submission, team.

## D5 · 13 Oct · Python + FastAPI, one main Cloud Run service + one fetcher
One runtime, one deploy; fetcher isolated for SSRF. See 02, 12.

## D6 · 13 Oct · Server writes, clients only read
All Firestore writes go through the backend (Admin SDK) after Pydantic validation; rules deny every client write. Cards immutable (`create()` only). See 12 §8.

## D7 · 13 Oct · ALTERED check = QR id + text diff + perceptual hash
Telegram recompresses photos, so image sha256 can't survive a forward. sha256 protects source snapshots and the canonical card record. See 03 §2.

## D8 · 14 Oct · Docs live in `context/`
Team lead's convention. Every PR updates SNAPSHOT + CHANGELOG, and ARCHITECTURE / DECISIONS when touched.

## D9 · 14 Oct · Team lead hands over frontend; no wait merges (supersedes part of D4)
Team lead (13 Oct 21:56Z): Agent builds everything, frontend included, and does not wait for approval. Agent opens one PR per phase and merges on green CI. Team lead's side shrinks to `externals/`.

## D10 · 14 Oct · Fetcher runs in process for now (supersedes part of D5)
The SSRF guard (`security.assert_public_https_url`) runs on every redirect hop, https and port 443 only, 2 MB cap, text content types only. A separate zero role fetcher service is better isolation; it's P5 hardening only if time allows. Residual risk: DNS rebinding between check and connect (documented in 12).

## D11 · 14 Oct · Prebunk jobs on Cloud Tasks with OIDC
`/api/prebunk` returns at once; the job runs via Cloud Tasks (retries, backoff) calling `/tasks/prebunk`, which accepts only a Google signed OIDC token for `api-sa`. Locally an in process queue does the same.

## D12 · 14 Oct · SQL = BigQuery analytics only
Firestore has no SQL. Team lead asked for a numbered `sql/` folder; it holds BigQuery views over the official Firestore export, used for the measured benchmark numbers.

## D13 · 14 Oct · Model never has the last word
Every evidence URL is fetched by us, a passage is matched, the page bytes are hashed and stored. If matched support is below 0.6, a hard verdict is downgraded to UNVERIFIABLE (`gate_verdict`). Numbers in a claim that don't appear in the passage cap support at 0.5.
