# Notices

Proof Card uses the following third party software and services. Licences read from each package's metadata (14 Oct 2026, pinned versions in `backend/requirements.txt` and `frontend/package.json`).

## Backend (Python)
| Package | Licence | Used for |
|---|---|---|
| FastAPI | MIT | API, share pages, websocket |
| Uvicorn | BSD-3-Clause | ASGI server |
| Pydantic, pydantic-settings | MIT | schemas, config |
| google-genai | Apache-2.0 | Gemini on Vertex AI (check, live transcription, embeddings) |
| firebase-admin | Apache-2.0 | ID token verification |
| google-cloud-firestore, -storage, -tasks, google-auth | Apache-2.0 | state, proof snapshots, jobs |
| httpx | BSD-3-Clause | own page fetch, Fact Check Tools API |
| trafilatura | Apache-2.0 | main text extraction from fetched pages |
| pypdf | BSD-3-Clause | PDF sources |
| RapidFuzz | MIT | fuzzy word match for Hindi / Hinglish passages |
| Pillow | MIT-CMU | card image rendering |
| NumPy | BSD-3-Clause (+ bundled permissive) | ALTERED band scores |
| ImageHash | BSD-2-Clause | perceptual hash |
| zxing-cpp | Apache-2.0 | QR reading on forwarded cards |
| python-multipart | Apache-2.0 | image upload |

## Frontend
| Package | Licence |
|---|---|
| React, React DOM | MIT |
| Firebase JS SDK | Apache-2.0 |
| Inter (@fontsource-variable/inter) | SIL OFL 1.1 |

## Fonts in card images
Noto Sans and Noto Sans Devanagari, SIL Open Font License 1.1, Google. Licence text: `backend/app/assets/fonts/OFL.txt`.

## Google services
Vertex AI Gemini, Google Search grounding, Google Fact Check Tools API (optional), Firestore, Cloud Storage, Cloud Tasks, Cloud Run, Firebase Hosting and Authentication, under the Google Cloud and Google APIs terms. Grounded explanations show Google's Search suggestion chips exactly as returned, as the grounding display rules require.

## Data
Benchmark labels in `backend/bench/h1_gold.jsonl` rest on public pages linked per row (mostly Wikipedia, CC BY-SA 4.0); we store only our own one line claims and the URLs, not page text. Snapshots fetched at runtime belong to their publishers and are kept only as evidence of what a page said at a time.

## Considered, not used
- langextract (Apache-2.0): structured extraction with source grounding. Not added: it pulls pandas, aiohttp, absl and more into the Cloud Run image, and our single Gemini call already returns the claim + evidence fields we need.
