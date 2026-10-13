# CONVENTIONS

## PRs
1. Agent posts the plan (requirement, approach, impact) in the DM first; PR goes up only after Team lead's ok.
2. Every PR updates `context/SNAPSHOT.md` + `context/CHANGELOG.md`, and `ARCHITECTURE.md` / `DECISIONS.md` when it changes them. No doc update = not mergeable.
3. CI must be green: ruff, format, mypy strict, pytest (coverage floor 85%), pip-audit, Firestore rules tests.
4. Max 2 open PRs at a time. Small PRs, one concern each.
5. Branch names: `p<phase>-<short-topic>`, e.g. `p1-backend-skeleton`.

## Docs
- Markdown only, never PDF.
- Every factual claim gets a clickable source and ✅ verified or 🟡 inference.

## Secrets
- Never in code, commits, issues, PR text or chat. Secret Manager only; keys reach Agent through a private drop link.

## Code
- Backend: Python 3.12, FastAPI, Pydantic v2, typed everywhere. Routes call the Store layer, never Firestore directly.
- Commit messages: imperative, short, prefix with phase (`p1: add firestore rules`).
