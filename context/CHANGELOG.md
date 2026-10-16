# CHANGELOG

Every PR adds one entry on top: date (IST), PR link, what changed, which context docs it touched.

## 2026-10-16 · v0.7.27 · p27-wayback-official
pib.gov.in refuses every Cloud Run request (403) and times out from every datacenter and proxy line tried; run 5 lost 50 of 108 facts to fetch failures, mostly PIB. The Wayback Machine holds dated copies of PIB press releases (PRID 1847862: 4 Aug 2022), and archive.org serves datacenter IPs.
- `app/facts.py`: when an OFFICIAL source refused us (403/401/429/timeout), `verify_candidate` reads its raw Wayback copy (`web.archive.org/web/<speech day>id_/<url>`, nearest snapshot) with the same gate: passage >= 0.35 and the figure on it. Kept as `checked: "archive"`, citing the archive URL. `official()` judges an archive URL by its original. Search grounding stays the last fallback. `stats.kept_archive` counts them.
- Docs touched: CHANGELOG, SNAPSHOT.

## 2026-10-16 · v0.7.26 · p26-dated-fact-bank
Prod run 5 on v0.7.25 (7dhIVHRKhvo, a 1 Aug 2022 speech): 108 researched, 10 kept (all official), 0 live lines decided. The bank held September 2026 figures; the speech cites the IMF's July 2022 cut (8.2% to 7.4%), so no fact ever matched the period of a line. 35 drops were low support on mospi.gov.in / rbi.org.in pages that do state the figure: the statement's attribution tail ("..., according to provisional estimates released by MoSPI") is never on the page and dragged the score to 0.04-0.27.
- `app/pipeline.py`: `youtube_published()` reads the publish date from the watch page (schema.org `datePublished` / `uploadDate`, or ytInitialData `publishDate`; oEmbed has no date). `Deps.video_date` wires it on prod. The prediction prompt and the fact research get the speech day.
- `app/facts.py`: `bank_key(topic, speaker, said_on)`: a dated speech has its own bank (`-dYYYYMMDD`). Angles, research and the rule prompt are told the date ("figures that were the latest ON THAT DATE, never one published after it"). `FactBankDoc.said_on` stored. 12 angles instead of 10 (parallel, no extra wall time). `verify_candidate` also matches `core_statement()` (the fact without its attribution tail; "per cent" kept); the figure must still be on the passage.
- Docs touched: CHANGELOG, SNAPSHOT.

## 2026-10-16 · v0.7.25 · p25-bank-survives-predict
Prod run on v0.7.24 (7dhIVHRKhvo brief): the MoSPI/RBI prompt worked. PIB 403 drops fell from 67 to 35, and the bank kept 9 facts, 8 of them official (MoSPI CPI + GDP press releases, IMF WEO Oct 2026, BEA). But Vertex was slow in that window (angles 182 s, against 4 s before), the claim prediction failed after the bank was built, and the whole session ended "failed" with its verified facts unused.
- `run_prebunk`: a prediction failure on a session whose linked fact bank holds facts ends it "ready" (no predicted claims, but every live line is still ruled against the bank). Without facts it still ends "failed".
- Docs touched: CHANGELOG, SNAPSHOT.

## 2026-10-16 · v0.7.24 · p24-blocked-official
Prod run on v0.7.23 (7dhIVHRKhvo brief): headers changed nothing. 96 researched, 2 kept, 67 drops still `pib.gov.in` 403 (an IP block on Cloud Run; it also times out from other datacenter and India proxy lines, and the Wayback Machine holds no copies).
- Research prompt: for Indian figures cite the issuing body's own page or PDF (mospi.gov.in, rbi.org.in, dea.gov.in, indiabudget.gov.in, data.gov.in) instead of the PIB copy.
- `verify_candidate`: when every source failed because an OFFICIAL host refused us (403/401/429/timeout) and Google Search grounding backed this exact statement from that same official host, the fact is kept with `checked="search"`, support 0.35, a passage that says so, and a `[search]` mark in the rule prompt. Anything else blocked stays dropped. Page-read facts rank first. `stats.kept_search` counts them.
- `chunk_hosts_for`: host of each grounding chunk (web.domain, else web.title when it is a hostname).
- Docs touched: CHANGELOG, SNAPSHOT.

## 2026-10-16 · v0.7.23 · p23-fetch-headers
Prod run on v0.7.22 (7dhIVHRKhvo brief): research found 84 facts, kept 4 (all official: IMF, World Bank, newsonair). 67 of the 80 drops were `pib.gov.in` answering 403 to the fetcher, 10 low support, 3 figure missing; research took 449 s of the 767 s brief.
- `app/proof.py`: crawler shaped User-Agent (`Mozilla/5.0 (compatible; ProofCardBot/0.3; ...)`, still names the bot) plus Accept and Accept-Language on every fetch. If PIB still blocks, the bank's `drop_fetch` count shows it on the next run.
- Docs touched: CHANGELOG, SNAPSHOT.

## 2026-10-16 · v0.7.22 · p22-fact-bank-diag
First prod run of the fact bank (7dhIVHRKhvo brief) kept 0 facts and the brief took 1042 s, against 361 s before. `match_passage` caps a window at 0.5 when any number in the query is missing from it, and a fact sentence states its figure AND its period, so the 0.45 bar dropped almost everything.
- `app/facts.py`: the keep bar is now the card gate (0.35) plus the figure on the page. Grounding chunks count as a fact's backup source when they cover >= 60% of its words (a JSON segment also holds keys, so Jaccard missed them). The answer parser takes the first JSON array of objects (`raw_decode`), so trailing text or citation marks like `[1]` no longer drop a whole angle.
- Diagnostics: every bank stores `stats` (stage seconds, empty angles, drop counts by reason: fetch, no_text, low_support, figure_missing, no_url) and up to 20 `samples` of dropped facts. An empty bank is stored and linked too, so `/api/sessions/:id/facts` says why research kept nothing. A failed rebuild never replaces a bank that already has facts.
- Docs touched: CHANGELOG, SNAPSHOT.

## 2026-10-16 · v0.7.21 · p21-fact-bank
Team lead (LC voice, 16 Oct): accuracy first, live speed later. Research 50-100 facts per topic as JSON, each with a source, store them separately and reuse them, and catch a false line against them. Weak sources fixed through research. Bank match was 0/6 on replay 7dhIVHRKhvo because spoken lines are worded differently from predicted claims.
- `app/facts.py` (new): research fact bank. Plan 10 angles, then 10 parallel grounded Gemini calls at 12 facts each (statement, value, as_of, source_url, trigger). A fact is kept only when its source page (the model's URL, or a grounding chunk whose segment overlaps the fact) is fetched, a passage on it scores >= 0.45, and the figure is in that passage. Official first, capped at 100.
- Stored as `fact_banks/{topic+speaker key}` and reused while it is under 7 days old with >= 20 facts. `GET /api/sessions/:id/facts` returns it as JSON (owner only).
- `app/pipeline.py` `verify_claim`: rules the line against the session's fact bank first. The judge picks the 1-3 facts that decide it (same measure, place, period), and the card cites those facts' pages through the same proof gate. No deciding fact, and the web check runs as before. `run_prebunk` attaches the bank before any claim is checked. A research failure costs the bank, never the brief.
- `ClaimDoc.fact_ids` and the live `proved` event carry `facts` (the deciding fact ids). `SessionDoc.fact_bank_key` links the bank.
- Tests: test_facts (build, verify, reuse, ruling guard, fact-first + fallback, prebunk attach, endpoint).
- Docs touched: SNAPSHOT, CHANGELOG, ARCHITECTURE, DECISIONS.

## 2026-10-16 · v0.7.20 · p20-predict-fallback
- Prod replay (Sitharaman, after #54): 2 of 3 briefs failed with 0 claims (80 s, 95 s), because the predict call hit the 40 s cap from #53.
- `app/pipeline.py` `_predict`: tries topic + video title with the speaker, then the bare topic with the speaker, then the bare topic alone. `app/model.py` PREDICT_TIMEOUT_S goes from 40 to 60.
- Tests: test_pipeline::test_prediction_drops_the_video_title_before_the_speaker.
- Docs touched: CHANGELOG.

## 2026-10-16 · v0.7.19 · p19-live-fit-check
Replay fit check on prod (Sitharaman Lok Sabha, 7dhIVHRKhvo): bank match 0/6, cards 108-145 s after the line, 4/6 lines no card and no reason, one UNVERIFIABLE card on legal500.
- `app/live.py` bank match: loose candidates (one side states no number or the numbers overlap, cosine >= 0.65) now reach the judge, top 3 by cosine, and count only on its yes. Exact numbers + cosine >= 0.90 still show at once, and with no judge (stub, tests) the old strict rule still applies.
- `app/live.py` cold checks run on their own 12-thread pool. They used to share the default `to_thread` pool, which has 5 threads on 1 vCPU, with spotter/match/Firestore.
- `app/pipeline.py` live path: the plain and speaker-country-hinted assess start together, and the plain card still wins. The bank keeps plain-then-hint, per #51.
- `app/pipeline.py` `Trace`: `failed`/`proved` events carry `stages` (ms per assess/fetch) and `reason` (no_evidence, low_support, fetch_failed, weak_sources_only, error).
- `app/pipeline.py` UNVERIFIABLE cards cite only reputable hosts (official, international, established newsrooms, fact checkers, Wikipedia). If none is left, there's no card.
- `app/pipeline.py` bank prediction gets the YouTube title via oEmbed when the brief has a video.
- Tests: test_live recall + reason, test_pipeline weak sources + race + video title.
- Docs touched: SNAPSHOT, CHANGELOG.

## 2026-10-16 · v0.7.18 · p7-comparison-one-line
- Prod regression on c668467 (brief 32aPEZxatdFuViIsQtmZWg): Hinglish per capita line now FALSE (was `failed`); the English line ended `failed` with a different grounded source set.
- `app/proof.py` `comparison_match`: one line that names every topic word and states two whole figures ("Japan's is $35,700, while India's is $2,810") is proof on its own; `_figures()` counts "$35,700" as one number, years excluded.
- Tests: `tests/test_comparison_proof.py::test_both_sides_in_one_sentence`.
- Docs touched: SNAPSHOT, versions/v0.7.18, CHANGELOG.

## 2026-10-16 · v0.7.17 · p7-viewer-reconnect
- Viewer link (spec §5, B1): owner toggles "Share viewer link" on `/s/:id/live` (`POST /api/sessions/{id}/share`, owner only); anyone with `/watch/:id` sees the live card stream on any phone, no audio, no sign in. Backed by public `GET /api/sessions/{id}/feed?since=` (opt in only, 404 otherwise, own token bucket `PC_FEED_RATE_PER_MIN`=60/min/IP, heard claims only, no owner fields), polled every 2 s, paused while the tab is hidden.
- `ClaimDoc.updated_at` stamped by both stores on every update, so the feed cursor catches claims proved after they were heard. `ClaimView.matched` so a resumed desk keeps PREBUNKED badges.
- Reconnect (spec B2): `connectLive()` retries a dropped socket with exponential backoff + jitter (0.5 s to 15 s, 8 tries, reset on `ready`), re-auths with a fresh ID token each time, shows "reconnecting…", then reloads `GET /api/sessions/{id}` and folds missed cards into the feed. 4401 and 1000 are final.
- Docs touched: SNAPSHOT, versions/v0.7.17, CHANGELOG, DECISIONS (D21).

## 2026-10-16 · v0.7.16 · p7-replay-mode
- `backend/app/clip.py`: `GeminiClipTranscriber.transcribe_timed` (Gemini 3.5 Flash, JSON `[{start:"MM:SS",text}]`), `parse_clock`, `timed_from_json`.
- `POST /api/sessions/{id}/clip?timed=true`; `LiveEngine.on_sentence(t_offset=)`; `ClaimDoc.t_offset_s`; `ClaimView` adds `matched_claim_id`, `t_offset_s`; events carry `t`.
- Frontend: YouTube IFrame Player API, `replayDue` / `clock`, "Replay with video" toggle, en + hi strings.
- Docs touched: SNAPSHOT, versions/v0.7.16, CHANGELOG.

## 2026-10-16 · v0.7.15 · p7-comparison-proof
- Prod check 16 Oct on 4e59b1f (brief sMHV3ThmpAigYXsuXqpsZQ): "India per capita GDP is higher than Japan." got model verdict FALSE (IMF: Japan $35,700, India $2,810), but the best 2 sentence window on worldometers scored 0.429 and the faithfulness gate showed UNVERIFIABLE. "India ka per capita GDP Japan se zyada hai" found no source over 0.35 and ended `failed`.
- Root cause: a comparison with no figure is proved by each side's figure, which a page states on separate lines (table rows 90 lines apart, metric in the caption). Window matching needs "higher than Japan" in one window; the contradiction path needs a number in the claim. Neither can fire.
- `app/proof.py`: `is_comparison()` (en / Hinglish / Devanagari relation words, no figure in the claim) + `comparison_match()`: one figure line per side (a year is not a figure) + the line naming the metric; score = topic words covered, relation words removed; fewer than 2 figure lines = no proof. `app/pipeline.py` `support_for` uses it for both verdict directions.
- Same page now scores 1.0 (header + Japan row + India row) for the English, Hinglish and possessive wordings.
- Tests: `tests/test_comparison_proof.py` (5).
- Docs touched: SNAPSHOT, versions/v0.7.15, CHANGELOG.

## 2026-10-16 · v0.7.14 · p7-telegram-alerts
- `backend/app/alerts.py`: `new_link` / `redeem` (deep link `t.me/<bot>?start=alert<sid><secret>`, sha256 only on the session, single use, 15 min) + `Alerter` (sendPhoto of `/v/<card>.png`, caption + "Open proof", FALSE / MISLEADING only, cap 10 per session).
- `POST /api/sessions/{id}/telegram-link` (owner only, 503 if the bot isn't configured). Bot `/start alert...` links the chat. `LiveEngine` fires alerts off the hot path on match and proved.
- Frontend: Live page button, en + hi strings.
- Docs touched: SNAPSHOT, versions/v0.7.14, CHANGELOG.

## 2026-10-16 · v0.7.13 · p7-no-silent-line (rev00012 bug 2 + stuck brief)
- Prod live check 16 Oct 07:3x UTC on 077b2a3: "India per capita GDP is higher than Japan." got `heard`, then nothing for 40 s+ on an open socket; a Trump brief socket died with a keepalive ping timeout while the bank was still prebunking; the earlier brief vVcm1NYvpjTuMkS2yAAxgQ sat in `prebunking` with 0 claims for 12 min.
- `app/live.py`: every heard line ends in `match`, `checking` or `skipped{reason}`. Spotter is bounded (`SPOT_TIMEOUT_S`); a model error or timeout falls back to the heuristic (check the whole line) instead of dropping it. One line that crashes is reported (`skipped error`), the socket lives on. A crashed cold check still resolves its tile as `failed`. Firestore calls in the live path run off the event loop.
- `app/model.py` `vertex_client()`: every Vertex call has a timeout (90 s generate, 10 s live path, 300 s clip) + SDK retries (3 attempts). google-genai has no default timeout.
- `app/pipeline.py` `run_prebunk`: a prediction failure ends the brief as `failed` (never stuck in `prebunking`); a Cloud Tasks redelivery finishes the same bank, never a second one. `app/tasks.py`: dispatch deadline 30 min (default 10 min retried a 7 min run that was still working).
- Frontend: Live shows why a heard line got no card; Brief shows "Couldn't build this brief" on `failed` and stops polling.
- Spotter prompt left as is: A/B on gemini-3.5-flash kept both per-capita lines with the current prompt; a recall-biased prompt also flagged "price of eggs out of control" (worse).
- Tests: `tests/test_rev00012_bug2.py` (9).
- Docs touched: SNAPSHOT, ARCHITECTURE, versions/v0.7.13, CHANGELOG.

## 2026-10-16 · v0.7.12 · p7-bank-speaker-language
- Prod live check (guest, wss, 16 Oct): English Trump brief bank came back 3/12 Hindi + Hinglish; "India per capita GDP is higher than Japan" was dropped by the pre filter (no digit, no superlative).
- `app/model.py` PREDICT_PROMPT 2026-10-16.1: claims in the language the speaker actually speaks, never translated to pad; include the speaker's already-rated claims.
- `app/live.py` `_NUMBERISH`: comparatives (higher/lower/more/fewer/worst/best/record/per capita/ahead of, zyada/kam/aage/peeche, Devanagari) reach the spotter.
- Tests: `test_predict_prompt_keeps_the_speakers_language`, `test_heuristic_lets_comparatives_through`.

## 2026-10-16 · v0.7.9 · p7-live-fast-judge
- `live.py`: `VertexJudge` (structured output `{same: bool}`, temperature 0) runs only for gray-zone candidates (`PC_LIVE_THRESHOLD` <= cosine < `PC_LIVE_INSTANT`, default 0.80/0.90). A no or a model error = cold check, never a wrong card.
- Latency: raw sentence is matched in parallel with the spotter call; a strong match pushes before the spotter returns. `LiveEngine.warm()` embeds the prebunked claims when the websocket opens (was: during the first sentence). 15 Oct live run measured 9.4 to 10.8 s heard to card.
- `_shown`: one prebunked card per session, however it is reworded.
- Docs touched: SNAPSHOT, versions/v0.7.9, CHANGELOG.

## 2026-10-16 · v0.7.8 · p7-live-match-number-guard (#30, with #28)
- `live.py`: a prebunked claim is a match candidate only if it states the same set of numbers as the heard claim (or both none). Fixes the 15 Oct live run where "repo rate 4% in 2025" borrowed the "4th largest economy by 2025" card (cosine 0.806) and "per capita GDP" borrowed a population card (0.846). A guard miss falls through to a cold check, never a wrong verdict.
- `pipeline.py` (#28): every source skip and every "no proof" logs a reason, so COULDN'T CHECK has a root cause in Cloud Logging.
- Docs touched: SNAPSHOT, versions/v0.7.8, CHANGELOG.

## 2026-10-16 · v0.7.7 · p7-guest-caps
- Anonymous auth & guest creation: "Continue as guest" on `/new`, backend accepts anonymous Firebase ID tokens for brief creation and live WebSocket sessions with strict owner isolation.
- Abuse protection: Firestore global daily cap on anonymous briefs (`prebunk_anon_daily_cap=100`) + per-UID 5-brief daily cap. Spoofed `X-Forwarded-For` cannot bypass caps. Generic detail on 500 error (`auth verification failed`).
- Frontend state: Zustand persistent app store for language and brief drafts.
- Telegram bot: commands set (`/start`, `/check`), help text fixed to `@ProofCardAgentBot`.
- Docs touched: skills.md, SNAPSHOT, versions/v0.7.7, CHANGELOG.

## 2026-10-14 · v0.7.6 · p6-repo-hygiene
- `.gitignore`: local docs with account details never commit (`context/Gemini_docs/`, `context/Gemini_docs.zip`, any `06_CREDENTIALS_AND_ACCOUNTS_REGISTRY.md` / `*CREDENTIALS*.md`). Moves the protection from one laptop into the repo, so every clone has it.
- One bucket name everywhere: `<project-id>-proofs` (E04 create, E08 `PROOF_BUCKET`, E09 `PC_PROOF_BUCKET`). Project ids are globally unique, so the bucket name is too, and the guide never mixes two names.
- `frontend/.env.example`: `VITE_LIVE_ORIGIN` listed (Cloud Run URL, needed for a manual prod build, same as `deploy.yml`).
- Docs touched: E04, E08, E09, SNAPSHOT, versions/v0.7.6, CHANGELOG.

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
