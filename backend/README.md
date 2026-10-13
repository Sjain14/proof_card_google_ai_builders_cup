# Proof Card backend

Prebunk claims before a stream, issue tamper evident proof cards after it, verify forwarded cards on Telegram.
Built fresh for the Google Cloud AI Builder Cup (Oct 14 to 18, 2026). Standards: `../context/12_Engineering_Standards.md`.

## Run locally

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env      # fill your own values, never commit .env
ruff check . && ruff format --check . && mypy app tests && pytest
uvicorn app.asgi:app --reload --port 8080
```

## Firestore rules tests (emulator, needs Java 11+ and Node 20)

```bash
cd ../rules-tests && npm ci
npx firebase emulators:exec --only firestore --project demo-proofcard --config ../firebase.json "npm test"
```

## Status

Phase 1: skeleton, auth, schemas, Firestore rules, webhook guard, SSRF guard, CI. Gemini pipeline, Cloud Tasks, fetcher service and Telegram replies land in phases 2 to 4.
