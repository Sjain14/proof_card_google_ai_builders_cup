# 07 · Features + Subfeatures (narrowed scope)

Labels: ✅ verified · 🟡 inference. Hours are our estimates 🟡. Owner: **L** = Agent (backend, Gemini pipeline, prebunk, bot, docs), **S** = Team lead + team (GCP account + deploy, frontend, video, submission).
Priority: 🔴 must for demo · 🟡 should · 🟢 stretch. InTruth column from our repo read ✅ (Proof_Card_vs_InTruth.md).

## A. Before: Prebunk Brief (hero)

| ID | Subfeature | What it does | FE | BE/MW/INT | Owner | InTruth? | Pri |
|---|---|---|---|---|---|---|---|
| A1 | Brief input | topic, speaker, YouTube link, context links, language | 3 h | 1 h | S, L | ❌ | 🔴 |
| A2 | Claim prediction | Gemini returns 10 to 15 likely claims as strict JSON, with "why likely" | | 4 h | L | ❌ | 🔴 |
| A3 | Pre verification | Fact Check Tools API → Search grounding → verdict + sources, via Cloud Tasks | | 6 h | L | ❌ | 🔴 |
| A4 | Faithfulness gate | check grounding support score; low → UNVERIFIABLE | | 3 h | L | ❌ | 🟡 |
| A5 | Embeddings + index | embed each claim, Firestore vector index | | 3 h | L | ❌ | 🔴 |
| A6 | Brief page | live grid via Firestore listener, progress | 5 h | | S | ❌ | 🔴 |

## B. During: Live bridge (thin)

| ID | Subfeature | What it does | FE | BE/MW/INT | Owner | InTruth? | Pri |
|---|---|---|---|---|---|---|---|
| B1 | Player + capture | YouTube IFrame + getDisplayMedia tab audio, 16 kHz PCM chunks over websocket | 6 h | | S | ✅ tab audio | 🔴 |
| B2 | Clip upload fallback | upload mp4/mp3, server transcribes | 1 h | 3 h | S, L | ❌ | 🔴 |
| B3 | Live transcription relay | websocket → Gemini Live / Speech-to-Text, Hinglish | | 6 h | L | ✅ (3rd party STT) | 🔴 |
| B4 | Claim spotting | is this sentence a checkable claim? fast model / langextract | | 3 h | L | ✅ inferred | 🔴 |
| B5 | Instant match | embed sentence, `find_nearest`, threshold → push existing card | | 3 h | L | ❌ | 🔴 |
| B6 | Cold check | miss → same pipeline as A3, status `checking` | | 1 h (reuse A3) | L | ✅ | 🔴 |
| B7 | Live feed UI | cards slide in, latency chip, PREBUNKED / LIVE badge | 5 h | | S | ✅ overlay | 🔴 |

## C. Proof of Source

| ID | Subfeature | What it does | FE | BE/MW/INT | Owner | InTruth? | Pri |
|---|---|---|---|---|---|---|---|
| C1 | Isolated fetcher | second Cloud Run, no IAM, private IP block, size/time caps | | 3 h | L (code), S (deploy) | ❌ | 🔴 |
| C2 | Snippet match | trafilatura text + RapidFuzz locate the supporting sentence | | 3 h | L | ❌ | 🔴 |
| C3 | Snapshot + sha256 | store text snapshot in GCS, hash on card | | 2 h | L | ❌ | 🔴 |
| C4 | Proof drawer | highlighted snippet, hash, fetched time | 3 h | | S | ❌ | 🔴 |

## D. After: Proof Capsule (hero)

| ID | Subfeature | What it does | FE | BE/MW/INT | Owner | InTruth? | Pri |
|---|---|---|---|---|---|---|---|
| D1 | Card record + id | canonical JSON + `card_sha256`, short id | | 2 h | L | ❌ | 🔴 |
| D2 | Verify page `/v/:id` | public SSR page + OG image | 4 h | 2 h | S, L | ❌ | 🔴 |
| D3 | Card PNG | Pillow render with verdict, id, QR; store pHash | | 4 h | L | ❌ | 🔴 |
| D4 | ALTERED check | image in → QR/id read → Gemini vision text extract → diff vs canonical + pHash distance | 2 h (upload UI) | 6 h | L, S | ❌ | 🔴 |

## E. Telegram (replaces WhatsApp)

| ID | Subfeature | What it does | FE | BE/MW/INT | Owner | InTruth? | Pri |
|---|---|---|---|---|---|---|---|
| E1 | Webhook + secret | `/tg/webhook`, secret header check, setWebhook script | | 2 h | L | ❌ | 🔴 |
| E2 | Forward check | photo → D4 → VERIFIED / ALTERED reply | | 2 h (reuse D4) | L | ❌ | 🔴 |
| E3 | Deep link | `?start=<id>` sends card + [Open proof] button | | 2 h | L | ❌ | 🔴 |
| E4 | Text lookup | text message → vector match → nearest card | | 2 h | L | ❌ | 🟡 |
| E5 | Inline share | inline mode, share card into any chat | | 3 h | L | ❌ | 🟢 |

## F. Language

| ID | Subfeature | FE | BE | Owner | Pri |
|---|---|---|---|---|---|
| F1 | Hindi / Hinglish / English in all prompts + UI strings | 2 h | 2 h | S, L | 🔴 |

## H. Benchmark

| ID | Subfeature | Effort | Owner | Pri |
|---|---|---|---|---|
| H1 | 50 claim set (Hindi/Hinglish/English) with gold labels + sources | 4 h | L drafts, S reviews | 🔴 |
| H2 | Runner: accuracy, latency prebunked vs cold, tamper detection on 20 edited cards | 3 h | L | 🔴 |
| H3 | `/about` page with numbers | 2 h | S | 🟢 |

## I. Platform

| ID | Subfeature | Effort | Owner | Pri |
|---|---|---|---|---|
| I1 | GCP project, APIs on, billing alert, service accounts, Secret Manager | 3 h | S | 🔴 |
| I2 | Firebase Hosting + Auth + App Check | 3 h | S | 🔴 |
| I3 | Cloud Run deploy x2 + Cloud Tasks queue + Firestore indexes | 4 h | S (L writes scripts) | 🔴 |
| I4 | Repo, README, licences file (third party notices) | 2 h | L | 🔴 |

## Counts and hours

- **Features:** 8 groups (A, B, C, D, E, F, H, I). **Subfeatures:** 34. **Must (🔴):** 30.
- **InTruth overlap:** B1, B3, B4, B6, B7 = 5. **New vs InTruth: 29 of 34.** (The live checker alandaitch/live-fact-checker also overlaps B only ✅ [repo](https://github.com/alandaitch/live-fact-checker).)

| Owner | Must hours | All hours |
|---|---|---|
| Agent (BE, pipeline, bot, docs, benchmark) | ~69 h | ~77 h |
| Team lead + team (FE, deploy, platform) | ~41 h | ~43 h |
| Video, deck, description, submission | ~10 h | ~10 h |
| **Total** | **~120 h** | **~130 h** |

🔴 Hard truth: the narrowed **must** list is still ~120 h. It "fits" only because Agent's ~69 h runs in parallel with the team's ~51 h. The team side is 51 h in 5 days = over 10 h/day for one person. With 2 to 4 humans it is fine; solo it is not. Second hard truth: what Agent writes still has to be reviewed, merged and deployed by Team lead on his GCP. Budget **~1.5 h/day of his time** just for review + deploy 🟡.

If time slips, cut in this order: E5, H3, E4, A4 (show support score only, no gate), B2. Never cut D4 or A3: those are the Innovation story.
