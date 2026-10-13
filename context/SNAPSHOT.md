# SNAPSHOT (where the build is right now)

Updated by every PR. Newest state only; history lives in CHANGELOG.md and `versions/`.

**As of:** 14 Oct 2026 IST · **Version:** v0.5.0 · **Phase:** P5 Live bridge

## Done
- v0.1.0 (PR #1): backend spine, auth, schemas, rules, guards, CI.
- v0.2.0 (PR #5): prebunk pipeline, proof snapshots, Cloud Tasks with OIDC, `sql/`.
- v0.3.0 (PR p3-proof-capsule): card PNG/JPEG with QR, ALTERED check (re-render + band diff), `/v/:id` share page, web image + text checks, Telegram bot (photo check, card lookup, inline share), checks logged without user ids. AGENTS.md + context/skills.md.
- v0.4.0 (PR p4-frontend): Vite + React + TS app (landing, new brief, live brief grid with share actions), Firebase Google sign in, Hosting rewrites to Cloud Run, CI frontend job.
- v0.4.1: judging criteria gate (`judging-criteria.md` + PR checklist), ASSETS.md, design system, rules test deps.
- v0.5.0 (PR p5-live-bridge): live websocket, Gemini Live transcription relay, claim spotting, instant match on embeddings, cold path, live page with player + tab audio + latency chips.
- Gates: backend ruff, format, mypy strict, pytest (89 tests, 98%), pip-audit; frontend tsc strict, vitest, build, npm audit.

## Needs his externals to go live
E03 to E10 (E05 web config for sign in), E15.

## Next
Deploy (his E03 to E10, then E09 with `--timeout 3600` + `VITE_LIVE_ORIGIN`), then on real services: tune the 0.80 match threshold on the demo clip (E11), benchmark runner H2 (latency, accuracy, tamper rate), clip upload fallback B2, visual QA of the deployed frontend, then demo video + deck (E12, E13).

## Blockers (owner)
- Repo public before submission (Team lead).
