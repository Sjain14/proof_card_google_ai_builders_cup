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

## D14 · 14 Oct · ALTERED = QR id + deterministic re-render + per band tile diff
The card layout is fixed (`card_image.BANDS`, `LAYOUT_VERSION`), so the server re-renders the original from the immutable card and compares each band (verdict, claim, explanation, sources) on blurred grayscale, taking the max over small tiles so a one word edit isn't diluted. Calibrated in `tests/test_capsule.py`: clean copies down to JPEG q30 at 50% scale score at most ~3, one word or number edits score 19+, threshold 8. Changing the layout means bumping `LAYOUT_VERSION` and keeping old renderers for old cards.

## D15 · 14 Oct · Fonts subset, docs first, no bloat (Team lead, 13 Oct 22:11Z)
`AGENTS.md` added: official docs before every integration (URL cited in code + PR), smallest complete change, deps pinned + recorded in `context/skills.md`, no third party installers. Noto fonts cut from 2.7 MB to 0.3 MB (subset to Latin + Devanagari, weight 400 to 700) with fontTools at dev time only.

## D16 · 14 Oct · Frontend: Vite + React + TS, no router or UI library
Three screens (Landing, New brief, Brief). A 15 line router and plain CSS with brand tokens beat two dependencies (AGENTS.md §2). The brief polls `GET /api/sessions/:id` every 1.5 s until done; a Firestore listener comes with live mode. `/v/:id` stays server rendered (v0.3.0) for link previews. Hosting rewrites `/api/**`, `/v/**`, `/tg/**` to Cloud Run, so everything is one origin (no CORS).

## D17 · 14 Oct · Live socket goes straight to Cloud Run
Firebase Hosting rewrites have a 60 s request timeout ✅ [docs](https://firebase.google.com/docs/hosting/cloud-run), so a live stream cannot ride them. The browser opens the websocket on the Cloud Run URL (`VITE_LIVE_ORIGIN`); Cloud Run supports websockets up to the service request timeout ✅ [docs](https://cloud.google.com/run/docs/triggering/websockets), deployed with `--timeout 3600`. Auth is the first message, not the URL, so ID tokens stay out of access logs. In prod the Origin must be on the allowlist (`PC_PUBLIC_BASE_URL` + `PC_LIVE_ORIGINS`), against cross site websocket hijacking.

## D18 · 14 Oct · Instant match in process, Vertex embeddings (supersedes the EmbeddingGemma + find_nearest line in 02/03)
A session holds at most 20 prebunked claims. Cosine over 20 unit vectors in memory takes well under a millisecond; a Firestore `find_nearest` round trip costs a network hop on the one path where latency is the demo. EmbeddingGemma on CPU would add a large runtime and model weights to the image (AGENTS.md §2). So: `gemini-embedding-001`, `SEMANTIC_SIMILARITY`, 768 dims ✅ [docs](https://ai.google.dev/gemini-api/docs/embeddings), index rebuilt only when the claim count changes. Upgrade path (marked `shortcut:` in `live.py`): `find_nearest` if a session ever holds hundreds of claims.

## D19 · 14 Oct · Claim spotting = cheap filter, then the model
Every final sentence passes a number / superlative filter first (English, Hindi, Hinglish words); only survivors cost a Gemini call (JSON array of claim spans). Chit chat never spends quota, and a repeated claim in one session makes one card, not two. Threshold for a PREBUNKED hit is 0.80 (`PC_LIVE_THRESHOLD`), to be re-tuned on the demo clip in E11.

## D20 · 14 Oct · Proof match: lexical + fuzzy + English restatement, contradiction counts for FALSE
Sources for Indian claims are mostly English; a Hinglish or Hindi claim cannot match them word for word. The assess call already reads the claim, so it also returns `CLAIM_EN` and we match on claim, `CLAIM_EN` and the grounding sentence, keeping the best. RapidFuzz absorbs inflections and spelling variants. A FALSE verdict is backed by an on topic passage that states a different number; a TRUE verdict still needs the claim's own numbers. Embedding based passage choice stays an option if the H2 benchmark shows misses (shortcut: lexical only, upgrade if Hinglish recall on H1 < 80%).

## D21 · 16 Oct · Viewer link = our polled feed, not a Firestore listener
Spec §5 suggested a Firestore listener for `/watch/:id`. Security rules allow or deny whole documents; they cannot hide a field, so a public read of `sessions/{id}` would expose `owner_uid` (and the prebunk bank in `claims`). Instead the API serves `GET /api/sessions/{id}/feed?since=`: opt in per session, 404 when off, heard claims only, an explicit response model with no owner data, rate limited per IP. Rules stay owner only. Polling every 2 s is enough for cards that take seconds to make. Shortcut: per instance token bucket and one Firestore list per poll; upgrade to a denormalised public `feeds/{id}` doc + listener if a session draws more than a few hundred viewers.
