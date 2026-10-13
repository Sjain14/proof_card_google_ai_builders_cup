# SNAPSHOT (where the build is right now)

Updated by every PR. Newest state only; history lives in CHANGELOG.md.

**As of:** 14 Oct 2026, 03:30 IST · **Phase:** P1 Spine (09_Dev_Plan_Phases.md)

## Done
- Context docs 00 to 12 in `context/` (scope locked: Before + After hero, live = thin bridge).
- Phase 1 backend scaffold built and green locally (not merged yet, PR waits on Team lead's ok): FastAPI service, Firebase ID token auth, Pydantic schemas for every request + Firestore doc, Firestore rules (deny by default), Telegram webhook secret check, SSRF guard, JSON logging with redaction, Dockerfile (non root), GitHub Actions CI.
- Local gates: ruff + format + mypy strict green, 38 pytest passing (97% coverage), 6/6 Firestore rules tests on emulator, pip-audit clean.

## In progress
- Phase 1 PR plan posted in DM, waiting for Team lead's ok.

## Next
- P1 rest: Gemini claim prediction (A2, A3), `verify_claim` Cloud Task, grounded check + proof snapshot (C1 to C3), local CLI exit test.

## Blockers (owner)
- Team no students confirmed before team formation closes on 14 Oct (Team lead).
- GCP project + APIs + Telegram bot token in Secret Manager (Team lead).
- Repo must be public by submission (Team lead, any time before 18 Oct).
