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
