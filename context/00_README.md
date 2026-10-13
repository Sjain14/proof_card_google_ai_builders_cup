# Proof Card · Context Docs (v1, 13 Oct 2026)

Scope = NARROWED, locked 13 Oct: **Before (Prebunk Brief) + After (Proof Capsule, Telegram) are the hero; live is a thin bridge from a pasted YouTube link; Pravachan, extension, caption scraping, MCP, A2UI cut.**
Split: Agent = backend, Gemini pipeline, prebunk, Telegram bot, docs, benchmark · Team lead + team = GCP account + deploy, frontend, video, deck, submission, team (no students).
Deadline: **18 Oct 2026, 11:59 PM IST** (we target 8 PM). Labels everywhere: ✅ verified with link · 🟡 our inference / estimate.

## Docs

| File | What's inside | Main criterion it serves |
|---|---|---|
| 01_PRD.md | problem, user, goals, non goals, requirements, metrics, open questions | Impact 25 |
| 02_Tech_Stack.md | every layer, why, Google vs open source, what changed from Stack v3, console checks | Tech + GenAI 40 |
| 03_Architecture_Integrations_APIs.md | diagram, 19 step demo spine, internal API, Firestore model, external APIs + limits, security | Tech + GenAI 40 |
| 04_User_Flow_Screen_Flow.md | user flow, 7 screens with states, Telegram flow, 3 min video storyboard | UX 10 |
| 05_UI_UX.md | principles, card anatomy, verdict states, accessibility, what not to build | UX 10 |
| 06_Brand_Guidelines.md | name, voice, colours, type, logo, assets (proposal, you lock) | UX 10 |
| 07_Features_Subfeatures.md | 8 features, 34 subfeatures, layers, owner, hours, InTruth overlap, cut order | all |
| 08_Reuse_Map.md | licence rules, libraries, what we learn vs never copy, competitor gap table, README credit | Innovation 25 |
| 09_Dev_Plan_Phases.md | pre code blockers, 5 phases with exit tests, daily rhythm, what Agent can and can't do, risks, submit checklist | delivery |
| 10_Criteria_Map_Deck_Submission.md | criterion → feature → proof on screen, template slide map, 1024 char description draft | all |
| 11_Your_Work_and_Setup.md | everything you and the team do: setup steps tonight, GCP/Firebase/Telegram, how PRs + deploys flow, your daily build list | delivery |
| 12_Engineering_Standards.md | security, auth, secrets, validation, SSRF, webhooks, Firestore schema + rules, codebase, tests + CI gates, threat model, what we skip | Tech + GenAI 40 |

**Dev memory (living, updated by every PR):** SNAPSHOT.md (where the build is now) · CHANGELOG.md (what changed, per PR) · ARCHITECTURE.md (current system, points to 03) · DECISIONS.md (why we chose what, ADR style) · CONVENTIONS.md (repo + PR rules)

## Hard truths (read first)

1. Must list is still **~120 hrs** (07). Works only with Agent ~69 h in parallel to team ~51 h. Solo on the team side = not doable.
2. Every PR needs your review + deploy. Budget ~1.5 h/day for that 🟡.
3. Image hash alone can't catch edits: Telegram/WhatsApp recompress photos 🟡. ALTERED = QR id + text diff + perceptual hash (03 §2).
4. Live input can't come from YouTube captions on Cloud Run (blocked from cloud IPs ✅ [issue #415](https://github.com/jdepoix/youtube-transcript-api/issues/415)). The pasted link plays in our page and we capture tab audio (Chrome), clip upload as fallback.
5. Theme fit is free for everyone in this track. Points come from the Before + After demo and Tech depth (10).
6. Odds (from verdict doc, 🟡): about 15 to 20% shortlist if all must items work + benchmark + clean video.

## Decisions needed from you (in this order)

1. Team + no students, **before team formation closes Oct 14** ✅ [FAQ](https://aibuildercup.com/Faqs.html)
2. Lock name + demo topic + demo clip
3. Repo (created Oct 14) + add Agent as collaborator
4. GCP project ready + Telegram bot token into Secret Manager (never in chat)
5. Lock phase P1 (09) so code starts

## Sources used

Our earlier docs (InTruth md, feature research md, verdict md, Stack v3, prior art, source ledger), your Cup data md + submission page + deck template, plus fresh checks today: Telegram Bot API page (secret token header, file limits ✅), GitHub API licences for langextract, trafilatura, RapidFuzz, imagehash, adk-python, youtube-transcript-api ✅, Google docs pages for Firebase Hosting + Cloud Run, Cloud Run websockets, App Check, Cloud Tasks, Fact Check Tools API, Model Armor, YouTube IFrame API, MDN getDisplayMedia ✅ (all opened, HTTP 200).
