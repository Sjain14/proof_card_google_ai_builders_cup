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

## Backend runtime dependencies added in v0.5.2 (proof path)
| Package | Version | Licence | Why |
|---|---|---|---|
| trafilatura | 2.3.1 | Apache-2.0 | main content extraction for proof snippets (08_Reuse_Map C2), drops menus / footers |
| pypdf | 6.20.1 | BSD-3-Clause | text layer of official PDF sources (pure Python, no system deps) |
| rapidfuzz | 3.14.6 | MIT | fuzzy token match in proof passages (08_Reuse_Map C2), C++ speed |

## Frontend dependencies (P4)
| Package | Version | Licence | Why |
|---|---|---|---|
| react, react-dom | 19.3.0 | MIT | UI |
| firebase | 13.0.0 | Apache-2.0 | Google sign in (modular SDK, only `app` + `auth` imported) |
| @fontsource-variable/inter | 5.3.0 | OFL-1.1 | brand font, self hosted (no third party font requests) |
| vite, @vitejs/plugin-react, typescript, vitest | 8.3.4, 6.1.2, 7.0.2, 5.0.4 | MIT / Apache-2.0 | build, typecheck, tests (dev only) |

No router and no UI library: 3 screens don't need them (D16).

Override: `@grpc/grpc-js` pinned to 1.14.6 via `overrides`. firebase 13 pulls 1.9.16 through Firestore's Node path (GHSA-m9gg-hp2v-232j, GHSA-f596-whhp-79r4, fixed in 1.13.6). We never import Firestore in the browser; the override keeps `npm audit` clean anyway.

## Assets
| Asset | Licence | Why |
|---|---|---|
| Noto Sans, Noto Sans Devanagari (subset) | SIL OFL 1.1 (`backend/app/assets/fonts/OFL.txt`) | deterministic card rendering in English + Hindi |
