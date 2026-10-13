# 02 · Tech Stack (Google max + open source)

Based on Stack v3 (sent 13 Oct), re-cut for the NARROWED scope. Labels: ✅ verified · 🟡 inference. Tags: [G] Google · [G+OSS] Google open source · [OSS] open source.

## Hard rule that drives the stack

✅ "All prototype submissions must integrate AI models such as the family of Gemini or Gemma models ... and prototypes must be deployed on Google Cloud Platform using Cloud Run or Firebase" ([aibuildercup.com](https://aibuildercup.com/), your "AI bUilders Cup data.md").
✅ The 1024 char brief description must say how we use **Firebase, Firestore, Cloud Run and Gemini** (your submission page file). So all four are mandatory in practice, not optional.

## The stack

| Layer | Pick | Why this, not something else | Tag |
|---|---|---|---|
| Hosting + web | Firebase Hosting, rewrites to Cloud Run ✅ [docs](https://firebase.google.com/docs/hosting/cloud-run) | one domain for app + API, free TLS, named in the brief | [G] |
| Auth | Firebase Auth (anonymous for viewers, Google sign in for admins) | verify page needs zero login; admin actions need identity | [G] |
| Abuse guard | Firebase App Check ✅ [docs](https://firebase.google.com/docs/app-check) | public demo link stays up through 3 weeks of evaluation; blocks scripted abuse of Gemini calls | [G] |
| Main backend | ONE Cloud Run service, Python + FastAPI: prebunk, live websocket, verify, card render, Telegram webhook | one runtime, one deploy. Cloud Run supports websockets ✅ [docs](https://cloud.google.com/run/docs/triggering/websockets) | [G] |
| Fetcher | tiny second Cloud Run service, no permission service account, egress limited | the only place untrusted URLs are fetched (SSRF isolation) 🟡 | [G] |
| Async jobs | Cloud Tasks → endpoint on main service ✅ [docs](https://cloud.google.com/tasks/docs) | retries for proof fetching without a worker service | [G] |
| Reasoning | Gemini on Vertex AI: fast Flash tier for claim spotting, stronger Flash for verdicts (exact model ids per Stack v3, confirm in console on Oct 14) 🟡 | judging requires Google models; Vertex keeps keys server side | [G] |
| Evidence | Fact Check Tools API first ✅ [docs](https://developers.google.com/fact-check/tools/api), then Google Search grounding ✅ [docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/grounding) | reuse existing fact checks before fresh search: faster + more credible | [G] |
| Faithfulness gate | Vertex check grounding API ✅ [docs](https://docs.cloud.google.com/generative-ai-app-builder/docs/check-grounding) | gives a support score; we refuse to show "FALSE" if the sources don't back it | [G] |
| Live speech | Gemini Live API transcription ✅ [docs](https://ai.google.dev/gemini-api/docs/live-api/live-transcribe); Cloud Speech-to-Text as fallback | Hinglish code mix quality: test both on day 1 with the demo clip 🟡 | [G] |
| Claim spans | langextract ✅ [repo](https://github.com/google/langextract) Apache-2.0, 38.9k stars | exact claim spans from transcript chunks | [G+OSS] |
| Embeddings | EmbeddingGemma (open weights) on CPU inside main service, OR Vertex text embeddings if cold start is bad 🟡 | Gemma use is visible to judges; fallback keeps the demo safe | [G+OSS] |
| Vector match | Firestore vector search `find_nearest` ✅ [docs](https://firebase.google.com/docs/firestore/vector-search) | no extra DB; same store as cards | [G] |
| Data | Firestore (sessions, claims, cards, jobs) + Cloud Storage (snapshots, card PNGs) | serverless, realtime listeners drive the UI | [G] |
| Page text | trafilatura ✅ [repo](https://github.com/adbar/trafilatura) Apache-2.0 | clean article text from cited pages | [OSS] |
| Snippet match | RapidFuzz ✅ [repo](https://github.com/rapidfuzz/RapidFuzz) MIT | fuzzy locate the quoted line in the page | [OSS] |
| Image check | imagehash ✅ [repo](https://github.com/JohannesBuchner/imagehash) BSD-2-Clause | perceptual hash of forwarded card vs issued card | [OSS] |
| Card render | Pillow + qrcode (Python) 🟡 licences: check on Oct 14 | PNG with verdict, id and QR | [OSS] |
| Telegram | raw HTTPS calls to Bot API ✅ [docs](https://core.telegram.org/bots/api) | no library licence question; webhook secret header supported ✅ | [OSS-free API] |
| Frontend | Vite + React + TypeScript + Tailwind + shadcn/ui | fast to build, Team lead owns it | [OSS] |
| Video embed | YouTube IFrame Player API ✅ [docs](https://developers.google.com/youtube/iframe_api_reference) | play the pasted link inside our page | [G] |
| Audio capture | `getDisplayMedia` tab audio ✅ [MDN](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia) + clip upload fallback | no extension; tab audio works best in Chrome 🟡 | [OSS] |
| Secrets | Secret Manager | bot token + signing secret never in code | [G] |
| Prompt injection | Model Armor on fetched page text ✅ [product](https://cloud.google.com/security/products/model-armor) | stretch: a hostile page can't steer verdicts 🟡 | [G] |
| Observability | Cloud Logging + Trace | show latency numbers in the demo | [G] |
| Cost guard | budget alerts, Cloud Run max instances | 3 weeks public link 🟡 | [G] |
| Eval | plain Python benchmark script (promptfoo optional) | 50 claim number for the deck | [OSS] |
| CI/CD | Cloud Build trigger from public GitHub repo (or `gcloud run deploy` by hand if short on time) | one push deploys | [G] |

## Changes from Stack v3 (and why)

| Removed | Why |
|---|---|
| A2UI cards, MCP tool, ADK wrapper | cut for scope; plain Python pipeline is enough and less to debug 🟡 |
| Document PiP over YouTube, wavesurfer timeline | UX polish, not judged enough to justify time 🟡 |
| GSAP motion | Tailwind transitions are enough |
| youtube-transcript-api server side | YouTube blocks transcript fetches from cloud IPs ✅ [issue #415](https://github.com/jdepoix/youtube-transcript-api/issues/415), [#511](https://github.com/jdepoix/youtube-transcript-api/issues/511) |
| grammY (Node) | backend is Python; raw Bot API calls are ~5 small functions 🟡 |
| Cloud Translation | Gemini handles Hinglish in prompts 🟡; add only if a judge facing language toggle is wanted |

## Google count (for the deck)

Firebase Hosting, Firebase Auth, App Check, Cloud Run x2, Cloud Tasks, Vertex AI Gemini, Fact Check Tools API, Search grounding, check grounding, Gemini Live / Speech-to-Text, EmbeddingGemma, Firestore + vector search, Cloud Storage, Secret Manager, Logging/Trace, Cloud Build, YouTube IFrame API, Model Armor (stretch) = **19 Google pieces** 🟡 count is ours. Open source: langextract, trafilatura, RapidFuzz, imagehash, Pillow/qrcode, React stack, all permissive.

## Confirm in console on Oct 14 (Team lead, 30 min)

1. Exact Gemini model ids available in his project + region.
2. check grounding API enabled + quota.
3. Fact Check Tools API key enabled.
4. Gemini Live transcription vs Speech-to-Text on 2 minutes of the demo clip (Hinglish).
5. EmbeddingGemma CPU latency on Cloud Run; else switch to Vertex embeddings.
