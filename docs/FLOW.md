# Proof Card: end-to-end flows

What a user does, what the app does, what they see and where the data lands, step by step, for every way in. Written from the code on `main` (16 Oct 2026, after #76). Anything not in the code is under "Known limits", not in a flow.

## 1. The user and the problem

AI makes fake news cheap: a politician's speech clipped and dubbed, a made-up quote typed onto their photo, a WhatsApp forward with three wrong numbers in it. By the time a fact-check article is out, the forward has done its work.

Who uses Proof Card:

| Who | When | What they need |
|---|---|---|
| Newsroom / fact-check desk | Before and during a speech or live stream | The claims the speaker is likely to make, checked before they say them, then a verdict within seconds of each line |
| Ordinary person | A forward or screenshot lands in a family group | One tap: is this true, with proof they can forward back |
| Group admin | A forward lands in their group | A bot that answers in the group, only when asked |
| Anyone who receives a card | A Proof Card image is forwarded to them | Check the card is the original and was not edited |

**The solution in one paragraph.** Proof Card checks claims against official data and trusted sources and hands back a **Proof Card**: the verdict (TRUE, MISLEADING, FALSE or UNVERIFIABLE), a one-line why, and the exact passage from each source page, with a hash of the page bytes we fetched. Before a speech it builds a **brief**: claims the speaker is likely to make, already checked, plus a **fact bank** of up to 100 verified facts (including World Bank official series for the speaker's country). During the speech, each line heard is matched against the brief in about a second; new claims get checked on the spot. The same engine answers on Telegram. Every card is an image with a QR and a fingerprint, so an edited copy is caught.

## 2. Flows

### (a) Web: a recorded YouTube speech

| # | User does | App does | User sees | Saved where |
|---|---|---|---|---|
| 1 | Opens the site | Serves the landing page (Firebase Hosting) | What Proof Card does, illustrative sample scenes (labelled as design samples), buttons to start a brief or open the Telegram bot | nothing |
| 2 | Clicks start, then "Continue as guest" (or Google sign-in) | Firebase Auth anonymous or Google sign-in | The new brief form | Firebase Auth user |
| 3 | Pastes only a YouTube link, clicks "Generate brief" (topic and speaker optional) | `POST /api/prebunk`: reads the video title as the topic when the topic is blank, creates the session, queues the brief job (Cloud Tasks) | The brief page, status "preparing" | `sessions/{id}` (owner, topic, speaker, youtube_url, status `prebunking`) |
| 4 | Waits on the brief page | `run_prebunk`: in parallel, Gemini predicts 12 claims and the fact desk researches the fact bank (grounded search + World Bank official pack); then each predicted claim is checked (`verify_claim`) | Predicted claims appear in about a minute, each turning from "checking" into a card; the fact bank count | `sessions/{id}/claims/{cid}`, `cards/{card_id}`, `fact_banks/{key}`, `claim_cards/{key}` |
| 5 | (nothing) | After 4 min the brief turns `ready`; slow claims keep checking and their cards still land | Status "ready" | session status `ready` |
| 6 | Opens the live page and uploads the audio of the clip (mp3, m4a, wav, ogg, webm, flac, up to 20 MB) | `POST /api/sessions/{id}/clip?timed=true`: Gemini transcribes the clip with timestamps; every sentence runs through the live engine (step b4) in the background; browser polls `GET /clip` | Progress "Checking the clip: x of y lines", then "Clip done" | clip bytes in Cloud Storage (by sha256), live claims with `t_offset_s` |
| 7 | Clicks "Replay with video" | Embeds the YouTube video; pops each card at the second it was said | Video on the left, cards appearing in sync | nothing new |
| 8 | Opens a card | `/v/{card_id}` on the API | Card page (see e) | nothing new |
| 9 | Optional: "Share viewer link" | `POST /api/sessions/{id}/share` turns on a public read-only feed | `/watch/{id}` link, polled every 2 s | session `public_view: true` |

### (b) Web: a scheduled live stream (not started yet)

| # | User does | App does | User sees | Saved where |
|---|---|---|---|---|
| 1 | Before it starts: creates a brief from the scheduled stream's link, or types topic + speaker | Same as (a) 3 to 5: predicted claims, fact bank, cards ready before the speaker starts | The brief, ready | as (a) |
| 2 | Optional: "Get FALSE / MISLEADING alerts on Telegram" | `POST /api/sessions/{id}/telegram-link` makes a one-time deep link `t.me/<bot>?start=alert...` (valid 15 min); the bot links that chat to the session on Start | Telegram opens on the bot with Start; bot confirms alerts are on | session `tg_link_hash`, `alert_chat_id` |
| 3 | When the stream goes live: opens it in a browser tab, opens the Proof Card live page, clicks listen and shares that tab with "Share tab audio" ticked | Browser captures tab audio (`getDisplayMedia`), streams PCM over a websocket (`/api/live/{id}`, auth = first message); Gemini Live transcribes, primed with names from the brief | "Listening" | session status `live` |
| 4 | Watches | Per sentence: spot the claims in it; match each against the brief's claims (embeddings, number check, judge); a match shows the ready card at once; a new claim is checked live (cache, fact bank, then search) | A feed: each line heard, then a card, a "checking" row that turns into a card, or the reason it was skipped (not checkable, repeat) | live claims + cards, as (a) |
| 5 | Gets a FALSE/MISLEADING card | Alerter sends it to the linked Telegram chat (max 10 per session), with a link to that second of the video when known | Telegram message with the card | nothing new |

The page can also receive typed lines (`{"type":"text"}` on the websocket), the path tests and the clip replay use.

### (c) Telegram bot

| # | User does | Bot does | User sees | Saved where |
|---|---|---|---|---|
| 1 | Sends a claim as text (4+ words) | Acks, checks it (cache, then the full check), max 10 checks per chat per day | "Checking this claim", then the card image with an "Open proof" button, or UNVERIFIABLE | a bot session + claim, `cards`, `claim_cards` |
| 2 | Forwards a long message (over 240 chars) | Splits it into up to 3 checkable claims, checks them in parallel; a split failure checks it whole | "Found n checkable claims", then one verdict per claim | as 1 |
| 3 | Sends a screenshot of a forward or a news graphic | Not a Proof Card: Gemini reads up to 3 claims off the image and checks them | As 2; nothing readable = "can't check" reply | as 1 |
| 4 | Forwards a Proof Card image | Reads the QR, re-renders the original, compares text + image hash | VERIFIED (original) or ALTERED (what changed), with the original's button | `checks` (result only: no chat id, user id or image) |
| 5 | Pastes a card link `/v/<id>` or `/start <id>` | Looks the card up | Card summary + button | nothing |
| 6 | In a group: adds the bot | Stays quiet on normal chat; answers forwards, `@bot <claim>`, `/check <claim>` and `/check <card-id>`; never posts help or errors in a group | Answers only when asked | as above |
| 7 | In any chat: types `@ProofCardAgentBot <card-id>` | Inline mode | The card to send into that chat | nothing |
| 8 | Taps "Get alerts" on the live page | Deep link with a one-time payload, see (b) 2 | Alerts on | session alert link |

### (d) "Did they really say it?" (PR #77)

| # | User does | App does | User sees |
|---|---|---|---|
| 1 | Sends a line like `Modi said: "..."`, `X ne kaha ki ...`, `मोदी ने कहा कि ...`, `"..." - X` (bot, brief or live) | Parses speaker + quote; grounded search for the original record; the quote's own words must be on a fetched page that names the speaker | TRUE "on record: did say this (proves the quote, not the statement)", MISLEADING "twisted: on record in other words", or, with no record, the normal fact check of the statement |

### (e) The card page and tamper check

| # | User does | App does | User sees |
|---|---|---|---|
| 1 | Opens `/v/{card_id}` | Server-rendered page | Verdict (English + Hindi), the claim, the why, Google search suggestion, each source with its passage, page sha256, fetch time; the card fingerprint; the card image with QR |
| 2 | Downloads a source hash | `GET /api/snapshots/{sha256}` returns the exact bytes we fetched | `sha256sum` of the file = the hash on the card |
| 3 | Uploads a copy of the card under "Got this card forwarded?" (or forwards it to the bot) | QR read, original re-rendered, text similarity + perceptual hash compared | VERIFIED or ALTERED banner on the page |
| 4 | Shares the card | `/v/{card_id}.png` is an immutable image; the page has Open Graph tags | Link preview with the card |

## 3. Data and reuse

Firestore (all writes are server-side, Admin SDK):

| Collection | Holds | Who can read (firestore.rules) |
|---|---|---|
| `sessions/{id}` | A brief / live session: owner, topic, speaker, YouTube link, status, fact bank key, clip job, alert link | Owner only (`get`/`list`) |
| `sessions/{id}/claims/{cid}` | Each predicted or heard claim: text, status, verdict, card id, second in the video | Session owner only |
| `cards/{card_id}` | Every Proof Card ever made (claim, verdict, why, sources with passages + page hashes, fingerprint) | Anyone by id (`get`), no listing |
| `fact_banks/{key}` | A researched fact bank (up to 100 facts, with sources) | Server only |
| `claim_cards/{key}` | Claim text (normalised) -> card id, for reuse | Server only |
| `checks/{id}` | Each VERIFIED / ALTERED / UNKNOWN check, result only | Server only |
| `daily_stats/{day}` | Counters for daily caps | Server only |

Page snapshots and clip audio go to Cloud Storage under their sha256.

Reuse, in the order a claim is checked (`verify_claim`):

1. **Saved card for the same claim**: `claim_cards` key = the claim text lower-cased with punctuation and spacing ignored, plus the speech link (empty for the bot, so every chat shares one verdict). Reused for 7 days. UNVERIFIABLE cards are never cached, so a later run can still find proof.
2. **The session's fact bank**: a Gemini ruling against the bank's verified facts. A bank is keyed by topic + speaker + the date the video was published, reused for 7 days, rebuilt if it holds under 20 facts.
3. **Live search**: grounded Gemini search, then we fetch each page ourselves, find the passage and snapshot the bytes. No passage, no card.

During a live session, every heard line is also matched against that session's predicted claims by meaning (embeddings + number check + judge), not by exact words.

Abuse caps: 5 briefs a day per guest, 20 per signed-in user, a global guest cap; 10 bot checks per chat per day; public endpoints rate-limited per IP.

## 4. Judging criteria map

| Criterion (weight) | Where it shows |
|---|---|
| C1 Technical merit and Gen AI (40%) | Gemini on Vertex for prediction, grounded research, rulings, image reading; Gemini Live transcription of tab audio; embeddings + judge matching in about a second; every card gated on a passage we fetched and hashed; Cloud Run, Cloud Tasks, Firestore, Firebase Hosting |
| C2 Problem alignment and impact (25%) | Built for Indian speeches and forwards: English, Hindi, Hinglish; World Bank official data; works where fake news travels (Telegram forwards, screenshots, groups) |
| C3 Innovation (25%) | Checked before the speaker says it (brief); tamper-evident card (QR + fingerprint + page hashes); fake quote check |
| C4 UX and solution design (10%) | Paste one YouTube link and wait; cards pop in sync with the video; one forward to the bot |

## 5. Known limits (honest)

- **Recorded YouTube video**: the app does not download YouTube. The user uploads the clip's audio (up to 20 MB), or plays the video in a tab and shares tab audio on the live page. The YouTube link gives the topic, the date and the replay player.
- **Live audio needs a desktop browser that can share tab audio** (Chrome / Edge). It does not pull a YouTube live stream by itself.
- **Reuse is exact-wording per claim** (normalised text). A differently worded claim reuses work only through the fact bank or, live, through the brief match; there is no cross-session similar-claim search over all saved cards yet.
- **Telegram buttons on `main`**: the landing "Open bot" link opens the bot with nothing preloaded, and a card's Telegram button shares the card link into a chat. Deep links that preload a message (`?start=`) exist only for alerts and card lookups. Being fixed in the how-to PR.
- **Card page repeats itself**: the server-rendered card page shows the claim and verdict in text and again in the card image at the bottom. Being fixed in the how-to PR.
- The fake quote check (d) is PR #77, not merged at the time of writing.
- Verdicts come from a model reading real pages; the passage and page hash let anyone check our reading, but the reading can still be wrong.
