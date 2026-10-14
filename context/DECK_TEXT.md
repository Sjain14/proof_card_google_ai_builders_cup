# DECK TEXT (prescribed template, slide by slide)

Labels: ✅ verified in the repo or on the official page · 🟡 inference / judgement.
Paste each block into the matching slide of the Cup template (14 content slides, slide map in [10_Criteria_Map_Deck_Submission.md](10_Criteria_Map_Deck_Submission.md) §2). Delete template slide 2 (its own instructions) before export. PDF ≤ 5 MB ✅.

Rules:
- Every `{{BENCH:...}}` comes from ONE committed vertex run file `backend/bench/results/<date>.json` (key path given), never typed by hand ✅ (bench README rule). Name the file in the slide footer.
- `{{E11:...}}` comes from `externals/inputs/e11_results.md`. `{{BQ:...}}` from the E15 views.
- Nothing on a slide that `SUBMISSION_DRAFT.md` §4 lists under "never claim".
- Criteria tags: C1 Tech + GenAI 40% · C2 Impact 25% · C3 Innovation 25% · C4 UX 10% ✅ ([FAQ](https://aibuildercup.com/Faqs.html)).

---

## Slide 1 · Team Details · (none, admin)
- Team name: `{{TEAM_NAME}}` (E02)
- Team leader: `{{LEADER}}`
- Members: `{{MEMBERS}}` (2 to 4, all 21+, JAPAC, no students ✅ FAQ)
- Challenge: Media, Content & Digital Experiences

## Slide 3 · Brief about the idea · C2, C3
**Proof Card: know the claim before it's said, and prove it after it's forwarded.**
- **Before.** Give a speech topic. Gemini predicts the claims and checks each against sources we fetch and hash ourselves.
- **During.** When a predicted claim is spoken, its card is already there. New claims are checked live.
- **After.** Every verdict is a card with a QR. Forward it to our Telegram bot: VERIFIED, or ALTERED with what changed.

Graphic: three columns Before / During / After, one card moving left to right.

## Slide 4 · Opportunities · C3, C2
**How is it different?** Fact checkers check a claim after someone pastes it. Proof Card checks the claims before the speech and keeps the proof attached to the card after it spreads.

| | Live claim check | Brief before the stream | Instant card on match | Hashed source snapshot | ALTERED check on a forward | Hindi / Hinglish |
|---|---|---|---|---|---|---|
| InTruth | ✅ | ❌ | ❌ | ❌ 🟡 | ❌ | Hindi 1 of 16 |
| live-fact-checker | ✅ | ❌ | ❌ | ❌ 🟡 | ❌ | 🟡 |
| Veritas / VeriFact (Devpost) | ❌ | ❌ | ❌ | 🟡 | ❌ 🟡 | 🟡 |
| **Proof Card** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

(Table from `08_Reuse_Map.md` §5, 🟡 = not seen in what we read.)

**How it solves it.** Prebunking works: warning people about a manipulation before they see it reduces its effect ✅ ([Science Advances](https://www.science.org/doi/10.1126/sciadv.abo6254)). Most fakes in India spread as forwarded screenshots; a card that can prove it was edited travels with the forward.

**USP: proof that survives the forward.**

## Slide 5 · List of features · C1, C4
- **Prebunk brief:** topic in, about 12 predicted claims, each checked with Google Search grounding (+ Fact Check Tools API when enabled).
- **Own proof:** we fetch every cited page, find the exact passage, store the page bytes under their sha256. No passage, no hard verdict ("Not enough proof").
- **Live:** tab audio or an uploaded clip, Gemini transcription, claim spotting, instant **PREBUNKED** match, cold path for new claims, latency on every card.
- **Proof Card:** image with verdict, QR and fingerprint; public verify page `/v/:id`, no login; download the source snapshot and recompute its hash.
- **Telegram bot:** forward a card, get **VERIFIED** or **ALTERED** with what changed; inline share from any chat.
- **Hindi + English + Hinglish:** Indic aware matching, Hindi UI toggle, Hindi verdict words on every card.

## Slide 6 · Process flow / use case · C4, C2
Use case: a newsroom or campaign desk preparing for a live speech.
1. Sign in with Google → New brief (topic, speaker, YouTube link).
2. Brief fills in: claims appear one by one, each with verdict + sources.
3. Go live: play the stream in the tab, start listening.
4. Spoken claim matches the brief → card in `{{BENCH:live.match_p50_ms}}` ms (PREBUNKED). New claim → checked live.
5. Share the card to Telegram; anyone forwards it to the bot → VERIFIED or ALTERED.

Diagram: the user flow in `04_User_Flow_Screen_Flow.md` §2.

## Slide 7 · Wireframes · C4
Real screenshots (not mockups): Landing, New brief, Brief grid, Live with feed, `/v/:id` on a phone, Telegram ALTERED reply.

## Slide 8 · Architecture · C1
As built (match the deployed system, nothing more):

```
Browser (React, Firebase Hosting + Auth) ──HTTPS / websocket──▶ Cloud Run: proofcard-api (FastAPI)
Telegram ──webhook + secret header──▶ Cloud Run
Cloud Run ──▶ Cloud Tasks ──OIDC──▶ Cloud Run (/tasks/prebunk)
Cloud Run ──▶ Vertex AI Gemini 3.5 Flash (predict, spot, assess) + Google Search grounding
          ──▶ Fact Check Tools API (when enabled)
          ──▶ Gemini 3.5 transcribe live / transcribe (audio), gemini-embedding-001 (match)
          ──▶ our fetcher (SSRF guard on every hop) ──▶ Cloud Storage snapshots/<sha256>
          ──▶ Firestore (sessions, claims, cards, checks)
```

Callouts: "the model never has the last word" (passage match gates the verdict) · "every source page hashed and downloadable".

## Slide 9 · Technologies · C1
**Google:** Vertex AI Gemini 3.5 Flash · Google Search grounding · Gemini 3.5 transcribe live + transcribe · Gemini embeddings · Fact Check Tools API (when enabled) · Cloud Run · Cloud Tasks · Firestore · Cloud Storage · Firebase Hosting · Firebase Auth · Secret Manager · Workload Identity Federation + GitHub Actions deploy · BigQuery (only if E15 done) · YouTube embed.
**Open source:** FastAPI, Pydantic, trafilatura, pypdf, RapidFuzz, Pillow, zxing-cpp (QR write + read), ImageHash, React, Vite (licences in `NOTICES.md`).

## Slide 10 · Implementation cost (optional) · C1
Only with real billing numbers after the first real runs (Cloud Billing report, 17 Oct): `{{COST_PER_1000_CHECKS}}` per 1,000 cold checks, `{{COST_PER_BRIEF}}` per brief. No real number → delete the slide 🟡.

## Slide 11 · Snapshots of the prototype · C4
Four real screenshots from the deployed link `{{PROTOTYPE_URL}}`: brief grid with verdicts, live feed with a PREBUNKED card and its ms chip, `/v/:id` on a phone with sources + hash, Telegram bot answering ALTERED.

## Slide 12 · Performance / benchmarking · C1
Source: `backend/bench/results/{{DATE}}.json` (vertex mode), 50 gold claims en / hi / hi-Latn.

| Metric | en | hi | hi-Latn |
|---|---|---|---|
| Verdict accuracy | `{{BENCH:by_lang.en.accuracy}}` | `{{BENCH:by_lang.hi.accuracy}}` | `{{BENCH:by_lang.hi-Latn.accuracy}}` |
| Proof rate (card with ≥ 1 hashed source) | `{{BENCH:by_lang.en.proof_rate}}` | `{{BENCH:by_lang.hi.proof_rate}}` | `{{BENCH:by_lang.hi-Latn.proof_rate}}` |
| "Not enough proof" rate | `{{BENCH:by_lang.en.unverifiable_rate}}` | `{{BENCH:by_lang.hi.unverifiable_rate}}` | `{{BENCH:by_lang.hi-Latn.unverifiable_rate}}` |

| Live + after | Value |
|---|---|
| Cold check latency p50 / p95 | `{{BENCH:overall.latency_p50_ms}}` / `{{BENCH:overall.latency_p95_ms}}` ms |
| Instant match rate on spoken paraphrases | `{{BENCH:live.instant_match_rate}}` |
| Instant match latency p50 / p95 | `{{BENCH:live.match_p50_ms}}` / `{{BENCH:live.match_p95_ms}}` ms |
| False match on chit chat | `{{BENCH:live.chitchat_false_match_rate}}` |
| Recompressed originals VERIFIED | `{{BENCH:tamper.clean_verified_rate}}` |
| Edited copies caught ALTERED | `{{BENCH:tamper.edit_caught_rate}}` |
| Real Telegram forwards (two phones) | `{{E11:pass_count}}` / 10 |

Footer: "Prebunked match is `{{BENCH:overall.latency_p50_ms}} ÷ {{BENCH:live.match_p50_ms}}` times faster than a cold check" (compute from the file, show the formula in notes).

## Slide 13 · Future development · C2, C3
- WhatsApp channel (Business API) next to Telegram.
- Browser extension: listen on any tab, no copy paste of links.
- Newsroom API: briefs and card verification for publishers.
- Pravachan mode: long form religious and political discourse in Indian languages.
- More Indian languages after Hindi (gold sets per language first).

## Slide 14 · Links · (all)
- Prototype: `{{PROTOTYPE_URL}}`
- Repo: `https://github.com/Sjain14/proof_card_google_ai_builders_cup`
- Demo video: `{{VIDEO_URL}}`
- Benchmark file: `backend/bench/results/{{DATE}}.json`
