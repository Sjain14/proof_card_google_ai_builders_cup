# SNAPSHOT (where the build is right now)

Updated by every PR. Newest state only; history lives in CHANGELOG.md and `versions/`.

**As of:** 16 Oct 2026 IST · **Version:** v0.7.18 · **Phase:** P7 Live testing & guest mode

## Done
- v0.1.0 to v0.5.0: backend spine, prebunk pipeline, proof snapshots, Cloud Tasks, card image + ALTERED check, `/v/:id`, Telegram bot, React frontend, live bridge.
- v0.5.x to v0.6.x (PRs #11 to #19): Gemini 3.5 Flash on global, transcribe live on global/us/eu, Hindi/Hinglish proof match, final transcription segments + custom vocabulary, prebunk rate limits + local stub run, public snapshot download, Fact Check Tools API behind a key, H1 gold set + H2 benchmark runner, README + NOTICES.
- v0.6.3 (#20) Search suggestion chips · v0.7.0 (#21) clip upload fallback · v0.7.1 (#22) Hindi UI.
- v0.7.2: `SUBMISSION_DRAFT.md` (description matching the real build) + `DECK_TEXT.md` (slide text per template, criteria tags, benchmark placeholders).
- v0.7.3: `deploy.yml` (WIF, merge to main → Cloud Run + Hosting) + manual `bench.yml` (vertex benchmark), `/api/health`.
- v0.7.5: Gemini audit fixes kept: `gs://` bucket accepted, E09 Cloud Tasks agent binding + env var escaping, E02 rename truth.
- v0.7.6: creds docs ignored in repo `.gitignore`, one bucket name `<project-id>-proofs` across E04/E08/E09, `VITE_LIVE_ORIGIN` in `frontend/.env.example`.
- v0.7.4: `externals/inputs/` templates (demo claims, E11 results), demo VO script + English `.srt` (`context/demo/`).
- v0.7.7 (#29): Guest mode ("Continue as guest"), Firestore global daily cap on anonymous briefs + per-UID 5-brief daily cap, Zustand persistent store, Telegram bot commands & help text fix.
- v0.7.8 (#28, #30): skip-reason logs for COULDN'T CHECK; live match needs the same stated numbers (15 Oct live run: 2 of 3 Hinglish lines borrowed a wrong card).
- v0.7.9: live gray-zone matches (0.80 to 0.90 cosine) need a Gemini "same claim?" judge; strong matches (>= 0.90, same numbers) push at once in parallel with the spotter; prebunk index embedded when the socket opens; a prebunked card shows once per session.
- v0.7.10 to v0.7.12 (#31 to #37): bank in the speaker's language, comparatives reach the spotter, faithfulness gate on the best source, bank seeded with the speaker's already rated claims (needs E16).
- v0.7.13: no silent live line (every `heard` ends in a card, a check or `skipped` with a reason), bounded Vertex calls, a brief never stuck in `prebunking`, retry-safe prebunk task.
- v0.7.14: Telegram alerts: "Get alerts on Telegram" on `/live/:id` → bot deep link (single use, 15 min, hash only) → FALSE / MISLEADING cards pushed as the card PNG + "Open proof", max 10 per session.
- v0.7.15: figure-less comparisons ("per capita GDP higher than Japan", Hinglish too) proved by each side's figure line + the metric line, so a FALSE stays FALSE instead of UNVERIFIABLE / `failed`.
- v0.7.16: Replay mode: clip upload on a brief with a YouTube URL is transcribed with MM:SS start times (`?timed=true`), each live claim stores `t_offset_s`, and "Replay with video" on `/live/:id` pops each card at that second of the embedded player.
- v0.7.17: read only viewer link `/watch/:id` (owner opt in, public polled feed) + live socket auto-reconnect with resume.
- v0.7.18: a comparison stated in ONE sentence (both figures) also counts as proof.
- v0.7.19: live fit check fixes: bank match recall through the judge, own cold check pool + parallel hint pass, failure reasons + stage times on live events, UNVERIFIABLE cards on reputable sources only, bank predicted from the video title.
- v0.7.21: research fact bank (50-100 source verified facts per topic + speaker, stored in `fact_banks`, reused for 7 days, JSON at `/api/sessions/:id/facts`); every claim is ruled against it before the web check.
- v0.7.22: fact bank keep bar = card gate + figure on page, sturdier answer parse, stored diagnostics (stage times, drop reasons, samples) even for an empty bank.
- v0.7.23: fetcher sends a crawler shaped UA + Accept headers (PIB 403'd 67/84 fact sources).
- v0.7.24: PIB blocks Cloud Run by IP: research cites MoSPI/RBI originals; a blocked official page counts only when Google Search grounding backs the statement from that same host (`checked: search`).
- v0.7.25: a failed claim prediction no longer fails a session that has a verified fact bank (it ends ready, live lines ruled against the bank).
- v0.7.26: fact bank anchored to the video's publish date (own bank per date, research + rulings told the speech day), 12 angles, facts matched without their attribution tail.
- v0.7.27: an official page that blocks our server (pib.gov.in) is read from its Wayback Machine copy nearest the speech day (`checked: archive`), still with passage + figure.
- v0.7.28: spotter pre filter + prompt take done deeds and absolutes ("I got all the hostages back", "we ended eight wars"); pure future pledges stay not checkable.
- v0.7.29: a TRUE card never rests on a page that only relays the speaker saying the claim (quote or "said he..."); the assess prompt judges the claim, not the quote.
- v0.7.30: the brief page keeps polling after a failed load (backoff up to 15 s, soft "retrying" note); only a 404 stops it.
- v0.7.31: a prebunk killed mid run (revision swap) resumes: the job beats on the session; a read that finds it silent 12 min re-queues it.
- v0.7.32: clip upload is a background job: POST /clip answers 202, the page polls GET /clip (progress + events); transcript and progress are stored, a stalled job resumes from its saved line.
- v0.7.33: the prebunk beat pulses every 60 s during fact research, so a long healthy research is never re-queued as stalled.
- Gates: backend ruff, format, mypy strict, pytest (171 passed, coverage 97.89%), pip-audit; frontend tsc strict, vitest (11 passed), build, npm audit; Firestore rules tests.

## Not built (never claim, see SUBMISSION_DRAFT.md §4)
Separate fetcher service · App Check · Firestore vector index · check grounding · EmbeddingGemma.

## Needs his externals to go live
E01, E03 to E10 (E05 web config for sign in), E16, E15, gold label review, E11, E12, E13.

## Next
After E03 + E08: first real run, fix what it surfaces, real benchmark file into DECK_TEXT.

## Blockers (owner)
- Repo public before submission, after a full history secrets scan (Team lead flips it).
