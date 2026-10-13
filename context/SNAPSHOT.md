# SNAPSHOT (where the build is right now)

Updated by every PR. Newest state only; history lives in CHANGELOG.md and `versions/`.

**As of:** 14 Oct 2026 IST · **Version:** v0.3.0 · **Phase:** P3 After (Proof Capsule + Telegram)

## Done
- v0.1.0 (PR #1): backend spine, auth, schemas, rules, guards, CI.
- v0.2.0 (PR #5): prebunk pipeline, proof snapshots, Cloud Tasks with OIDC, `sql/`.
- v0.3.0 (PR p3-proof-capsule): card PNG/JPEG with QR, ALTERED check (re-render + band diff), `/v/:id` share page, web image + text checks, Telegram bot (photo check, card lookup, inline share), checks logged without user ids. AGENTS.md + context/skills.md.
- Gates: ruff, format, mypy strict, pytest (89 tests, 98% coverage), pip-audit clean.

## Needs his externals to go live
E03 to E10, E15.

## Next
P4 frontend (admin brief screen, card grid, Firebase Hosting with rewrites to Cloud Run).

## Blockers (owner)
- Repo public before submission (Team lead).
