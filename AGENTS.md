# AGENTS.md · rules for any coding agent (or human) working in this repo

This is the ONE instructions file (Team lead, 13 Oct). Follow all of it, always. Add new instructions here, never in a second file. Details: `context/CONVENTIONS.md`, `context/12_Engineering_Standards.md`.

## 0. Team lead's standing instructions
- Market gold standard best practice everywhere: backend, security, functionality, database structure, codebase. It must actually work, fully integrated, no shortcuts.
- Every feature must serve the judging criteria (`context/10_Criteria_Map_Deck_Submission.md`). Target: high end, completely working, selected for Singapore.
- Don't wait for approval: one PR per phase, verify + validate, merge on green CI. Plan goes in the PR description.
- Docs live in `context/` (SNAPSHOT, version history, ARCHITECTURE, DECISIONS, CHANGELOG), updated in every PR.
- Human only work goes to `externals/` as step by step task files.
- SQL lives in `sql/` as `01_name.sql`, `02_name.sql`, ... (run in number order).
- Progress update to Team lead every 30 minutes while building; don't miss anything.
- Research the market before building; use the strongest model for complex reasoning (backend), and a frontend approach that produces genuinely beautiful, non generic UI.
- Assets may be collected from the internet (licence checked, credited); animations must be beautiful but light.
- Before each task, look for an existing expert skill for it and use it (within §3 below: adopt the text and ideas, never run third party installers).
- Verify everything. Read the official, latest docs for every integration (§1). No sloppy work, no bloat (§2).

## 1. Official docs before every integration
- Before touching any external service, API, SDK or GCP product (Vertex AI / Gemini, Cloud Run, Cloud Tasks, Firestore, Cloud Storage, Firebase, BigQuery, Telegram Bot API), read the **current official documentation** for the exact version we pin. Not blog posts, not memory, not old examples.
- Cite the doc URL in the code comment at the integration point (one line) and in the PR description under **Docs read**.
- If the docs and our code disagree, the docs win; fix the code in the same PR.

## 2. No bloat
The smallest change that fully solves the task wins. In order, take the first that works:
1. Does it need to exist? Skip features, options and "for later" code nobody asked for.
2. Already in this repo? Reuse it the way the surrounding code does.
3. Standard library or a platform feature? Use it.
4. An already pinned dependency? Use it. Never add a dependency for a few lines.
5. Otherwise, the minimum code that works.

Never cut: validation at trust boundaries, error handling that prevents data loss, security, accessibility, tests for non trivial logic.

No dead code, no unused deps, no generated junk (caches, coverage files, build output, lockfile churn) in commits. A known shortcut gets a comment: `shortcut: <limit>, <when to upgrade>`.

**PR review checks**: diff size is justified by the task, every new dependency is listed with a reason, nothing unused ships.

## 3. Dependencies and tools
- A new project dependency must be a well known package, pinned to an exact version, licence checked, and recorded in `context/skills.md` with why.
- Never download and run third party scripts, installers, CLIs or hooks inside the dev environment. Read their docs and adopt the ideas; markdown skill text may be adapted (with credit), executables may not be installed.

## 4. Every PR
Plan in the PR description, docs updated (SNAPSHOT, CHANGELOG, versions/, ARCHITECTURE / DECISIONS when touched), CI green, then merge (D9).

Credit: section 2 adapts ideas from the MIT licensed [Ponytail](https://github.com/DietrichGebert/ponytail) skill.
