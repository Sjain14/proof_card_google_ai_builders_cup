# SNAPSHOT (where the build is right now)

Updated by every PR. Newest state only; history lives in CHANGELOG.md and `versions/`.

**As of:** 16 Oct 2026 IST · **Version:** v0.7.9 · **Phase:** P7 Live testing & guest mode

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
- Gates: backend ruff, format, mypy strict, pytest (149 passed, coverage 97.94%), pip-audit; frontend tsc strict, vitest (11 passed), build, npm audit; Firestore rules tests.

## Not built (never claim, see SUBMISSION_DRAFT.md §4)
Separate fetcher service · App Check · Firestore vector index · check grounding · EmbeddingGemma.

## Needs his externals to go live
E01, E03 to E10 (E05 web config for sign in), E16, E15, gold label review, E11, E12, E13.

## Next
After E03 + E08: first real run, fix what it surfaces, real benchmark file into DECK_TEXT.

## Blockers (owner)
- Repo public before submission, after a full history secrets scan (Team lead flips it).
