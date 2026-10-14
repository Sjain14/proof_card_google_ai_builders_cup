# SUBMISSION DRAFT (Hack2skill form, E13)

Labels: ✅ verified in the repo or on the official page · 🟡 inference / judgement.
Rule: the form only says what runs on the deployed link on submit day. Every sentence below maps to code (table in §3). Deck text lives in [DECK_TEXT.md](DECK_TEXT.md).

## 1. Form fields

| Field | Value |
|---|---|
| Challenge | Media, Content & Digital Experiences ✅ (`10_Criteria_Map_Deck_Submission.md`) |
| Prototype link | `https://<project>.web.app` (from E09) |
| Repo link | `https://github.com/Sjain14/proof_card_google_ai_builders_cup` (public only after the history secrets scan, E13 step 7) |
| Demo video | YouTube unlisted link (E12) |
| Deck | PDF ≤ 5 MB from the prescribed template, text from `DECK_TEXT.md` |
| Description | §2, ≤ 1024 chars, must name Firebase, Firestore, Cloud Run, Gemini ✅ (form rule) |

## 2. Brief description

### Version A (default: Fact Check key set, E16 done, live transcription works on the demo clip)

> Proof Card fights misinformation before, during and after a video. Before a speech, Gemini on Vertex AI predicts the claims a topic or speaker is likely to make and checks each with Google Search grounding and published fact checks from the Fact Check Tools API. We fetch every cited page ourselves, find the exact passage that backs or refutes the claim, and store the page bytes under their sha256 in Cloud Storage. No passage, no hard verdict. During playback, Gemini live transcription feeds claim spotting and Gemini embeddings match each spoken claim to the prebunked set, so its card appears instantly; new claims are checked live. After, every verdict is a Proof Card image with a QR and a public verify link. Forward a copy to our Telegram bot and it answers VERIFIED, or ALTERED with what was edited. Hindi, English and Hinglish. Built on Cloud Run, Cloud Tasks, Firestore, Cloud Storage, Firebase Hosting and Firebase Auth.

934 chars (counted with `len()`, recount after any edit).

### Swaps (apply only the ones that are true on submit day)

| If | Replace | With |
|---|---|---|
| E16 not done (no `PC_FACTCHECK_API_KEY`) | ` and published fact checks from the Fact Check Tools API` | (delete) |
| Demo uses the clip upload path, not tab audio | `Gemini live transcription feeds claim spotting` | `Gemini transcribes the stream or an uploaded clip, feeds claim spotting` |
| Telegram forward test (E11) below 8/10 | `Forward a copy to our Telegram bot and it answers` | `Send a copy to our Telegram bot or the verify page and it answers` |

## 3. Every claim in the description → where it is in code

| Claim | Where ✅ |
|---|---|
| Gemini on Vertex AI predicts claims | `backend/app/model.py` (VertexModel, default `gemini-3.5-flash`, `PC_GEMINI_REGION=global`) |
| Google Search grounding | `backend/app/model.py:208` (`types.Tool(google_search=...)`), suggestion chips shown per grounding rules (PR #20) |
| Fact Check Tools API | `backend/app/factcheck.py`, only when `PC_FACTCHECK_API_KEY` is set (PR #17) |
| We fetch every page ourselves | `backend/app/proof.py` HttpFetcher, SSRF guard on every redirect hop (`backend/app/security.py`) |
| Exact passage | `backend/app/proof.py` (trafilatura / pypdf text, RapidFuzz match, Devanagari + Hinglish aware, PR #13) |
| sha256 in Cloud Storage | `backend/app/proof.py` GcsSnapshots, `snapshots/<sha256>`, create only |
| No passage, no hard verdict | `gate_verdict` in `backend/app/schemas.py:147` → UNVERIFIABLE |
| Gemini live transcription | `backend/app/live.py` GeminiLiveTranscriber (`gemini-3.5-transcribe-live`) |
| Clip fallback | `backend/app/clip.py` (`gemini-3.5-transcribe`, PR #21) |
| Gemini embeddings match | `backend/app/live.py` VertexEmbedder (`gemini-embedding-001`), cosine ≥ 0.80 in process |
| Proof Card image + QR + verify link | `backend/app/card_image.py`, `backend/app/share_page.py` (`/v/:id`) |
| Telegram bot VERIFIED / ALTERED | `backend/app/telegram.py`, `backend/app/alter.py` |
| Hindi, English, Hinglish | matching (PR #13), UI toggle (PR #22), gold set per language (`backend/bench/h1_gold.jsonl`) |
| Cloud Run, Cloud Tasks, Firestore, Firebase Hosting + Auth | `backend/Dockerfile`, `backend/app/tasks.py`, `backend/app/store.py`, `firebase.json`, `frontend/src/auth.ts` |

## 4. Never claim (not in code, 14 Oct re check) 🔴

| Earlier draft said | Truth in repo ✅ |
|---|---|
| Isolated fetcher on its own Cloud Run | Fetcher runs inside the API service; SSRF guard only, no separate service |
| Firebase App Check | 0 references in `frontend/` or `backend/` |
| Firestore vector search | No vector index in `firestore.indexes.json`; match is in process cosine (`backend/app/live.py:201`) |
| Vertex check grounding score | No check grounding call; the support score is our own passage match |
| EmbeddingGemma | Embeddings are `gemini-embedding-001` |

If any of these get built before 18 Oct, move the row to §3 with its file and only then add it to §2.

## 5. Submit day check
1. Recount §2 (≤ 1024).
2. Each swap in §2 decided from a real run, not from memory.
3. Open all four links logged out / incognito.
4. Screenshot the confirmation.
