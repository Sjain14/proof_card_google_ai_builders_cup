# SNAPSHOT (where the build is right now)

Updated by every PR. Newest state only; history lives in CHANGELOG.md and `versions/`.

**As of:** 14 Oct 2026 IST · **Version:** v0.2.0 · **Phase:** P2 Before (prebunk pipeline)

## Done
- v0.1.0 (PR #1, merged): backend spine, auth, schemas, rules, webhook + SSRF guards, CI.
- v0.2.0 (PR p2-prebunk-pipeline): Gemini claim prediction + grounded assessment, our own fetch + passage match + sha256 snapshots, faithfulness gate, prebunk job via Cloud Tasks with OIDC, owner only session view, offline stub mode, `sql/` BigQuery views.
- Gates: ruff, format, mypy strict, pytest (64 tests, 98% coverage), pip-audit clean.

## Works without Team lead's setup
Everything above, offline (`PC_MODEL_MODE=stub`, in memory store in tests).

## Needs his externals to go live
E03 to E10 (project, APIs, Firebase, service accounts, bot token, deploy, model check), E15 (BigQuery).

## Next
P3 After: card PNG with QR id, ALTERED check (text diff + pHash), Telegram bot replies, inline share, `/v/:id` share page.

## Blockers (owner)
- E01 team no students before 14 Oct close (Team lead).
- Repo public before submission (Team lead).
