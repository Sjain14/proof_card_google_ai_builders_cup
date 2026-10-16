# Proof Card

An authenticity checker for what leaders say. AI can fake a speech, an anchor or a headline in seconds; Proof Card checks what a politician, a news clip or a forward actually claims against official data, shows the exact passage that decides it, and turns every verdict into a tamper evident card anyone can verify on Telegram. Not a transcription tool: transcription is only the input, the product is the proof.

Google Cloud AI Builder Cup 2026 · Media, Content & Digital Experiences track.

- Project docs, plans and dev memory: [`context/`](context/00_README.md)
- Where the build is right now: [`context/SNAPSHOT.md`](context/SNAPSHOT.md)
- Human setup steps (GCP, Firebase, Telegram, deploy): [`externals/`](externals/README.md)

## How it works
1. **Prebunk.** Give a topic and speaker. Gemini predicts the claims likely to come up and checks each with Google Search grounding (and, if `PC_FACTCHECK_API_KEY` is set, published fact checks from the Fact Check Tools API first).
2. **Own proof.** We fetch every cited page ourselves, extract the main text (trafilatura, PDFs via pypdf), find the passage that supports or contradicts the claim (Hindi, Hinglish and English), and store the exact bytes under their sha256. No passage, no hard verdict: the card says UNVERIFIABLE.
3. **Live.** During the stream, live transcription feeds claim spotting; a sentence that matches a prebunked claim gets its card instantly, new claims go down the cold path.
4. **Ask the bot.** Send any claim or forward to the Telegram bot: it runs the same check and answers with the verdict, the source passage and a shareable card.
5. **Proof capsule.** Every card is an image with a QR. Forward it anywhere; anyone can send it to the Telegram bot or `/v/<id>` to get VERIFIED or ALTERED (which part was edited), and download any source page (`/api/snapshots/<sha256>`) to recompute its hash.

## Stack
FastAPI on Cloud Run · Vertex AI Gemini (`gemini-3.5-flash`, live `gemini-3.5-transcribe-live`, `gemini-embedding-001`) · Firestore · Cloud Storage · Cloud Tasks · Firebase Hosting + Auth · React + Vite · Telegram Bot API.

## Run locally (no GCP needed)
```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env            # PC_MODEL_MODE=stub, PC_ENV=local
PC_AUTH_DISABLED=true uvicorn app.asgi:app --port 8080   # in memory store, fixture model
pytest                          # ruff, mypy strict and 85% coverage gate run in CI too
python -m bench.run --mode stub # benchmark harness wiring check

cd ../frontend && npm ci && npm run dev   # npm test, npm run build
```
Stub mode uses fixtures and an in memory store: no Google credentials, nothing persisted. Real services: set `PC_MODEL_MODE=vertex` + `PC_GCP_PROJECT` (see `externals/E03` to `E09`).

## Benchmark
`backend/bench/`: H1 gold set (50 source linked claims, en / hi / hi-Latn) and the H2 runner (accuracy, proof rate, latency p50 / p95, instant match, tamper). Every number we quote comes from a committed run. See [`backend/bench/README.md`](backend/bench/README.md).

## Credits and licences
Built on open source and Google services; full list with licences in [`NOTICES.md`](NOTICES.md). Fonts: Noto Sans + Noto Sans Devanagari (SIL OFL 1.1, `backend/app/assets/fonts/OFL.txt`).
