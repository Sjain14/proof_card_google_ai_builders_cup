# skills.md · tools, skills and dependencies we use (and why)

Rule (AGENTS.md §3): every dependency pinned, licence checked, reason given. No third party installers or hooks run in the dev environment.

## Agent skills / methods
| Name | What it is | Used? |
|---|---|---|
| Ponytail ([repo](https://github.com/DietrichGebert/ponytail), MIT) | Markdown skill: "smallest complete change" coding discipline | ✅ ideas adapted into AGENTS.md §2. Nothing installed. |
| Graph memory MCP servers, e.g. [mnemograph](https://github.com/tm42/mnemograph), [memory-graph](https://github.com/memory-graph/memory-graph) | Persistent agent memory over MCP | ❌ not used. Our memory is the `context/` folder (SNAPSHOT, ARCHITECTURE, DECISIONS, CHANGELOG), which is versioned, reviewable and public. An MCP server would mean running third party code for no gain here. |

## Backend runtime dependencies added in P3
| Package | Version | Licence | Why |
|---|---|---|---|
| zxing-cpp | 3.1.1 | Apache-2.0 | QR create + read for the card id (one lib for both, no OpenCV) |
| ImageHash | pinned in requirements.txt | BSD-2-Clause | perceptual hash recorded for ALTERED analytics |
| numpy | pinned in requirements.txt | BSD-3-Clause | band diff math in the ALTERED check (already pulled by ImageHash) |
| python-multipart | 0.0.32 | Apache-2.0 | FastAPI file upload on the share page check form |

## Assets
| Asset | Licence | Why |
|---|---|---|
| Noto Sans, Noto Sans Devanagari (subset) | SIL OFL 1.1 (`backend/app/assets/fonts/OFL.txt`) | deterministic card rendering in English + Hindi |
