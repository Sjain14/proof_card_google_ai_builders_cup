# 09 · Development Plan + Phases (Oct 14 to Oct 18, 11:59 PM IST)

Labels: ✅ verified · 🟡 estimate / plan. Owner **L** = Agent, **S** = Team lead + team.

## 0. Before code (tonight / Oct 14 morning, blocks everything)

| # | Item | Owner | Why it blocks |
|---|---|---|---|
| 0.1 | Team final + **no students** confirmed; formation closes **Oct 14** ✅ [FAQ](https://aibuildercup.com/Faqs.html) | S | whole team DQ otherwise ✅ |
| 0.2 | Lock name, demo topic, demo clip (2 to 4 min, Hinglish, has checkable numeric claims) | S | prebunk + benchmark depend on it |
| 0.3 | Public GitHub repo created **on Oct 14** (fresh project ✅), Agent added as collaborator | S | L can't push without it |
| 0.4 | GCP project + billing alert + APIs on (Vertex, Firestore, Run, Tasks, Storage, Secret Manager, Fact Check Tools) | S | nothing deploys |
| 0.5 | Telegram bot token from BotFather → straight into Secret Manager, never in chat | S | E1 |
| 0.6 | Repo rule: L posts plan per PR, raises PR after Team lead's ok, every PR ships its doc note (your existing PR rules) | both | review flow |

## 1. Phases

| Phase | Day | Goal | L builds | S builds | Exit test (must pass before next phase) |
|---|---|---|---|---|---|
| **P1 Spine** | Oct 14 | claim in, verdict + proof out | A2, A3, C1 to C3, D1, Firestore schema, `verify_claim` task, local CLI | I1 to I3, Vite app skeleton, Auth, Hosting rewrite | CLI: 1 topic → 12 claims with verdict, sources, snapshot hash in Firestore |
| **P2 Before** | Oct 15 | Prebunk Brief end to end in browser | A5 embeddings + index, D3 PNG, D2 `/v/:id` server side, H1 claim set draft | A1, A6 brief page, D2 styling | deployed URL: create brief, cards appear live, `/v/:id` opens on phone |
| **P3 After** | Oct 16 | Proof Capsule + Telegram (the riskiest new part, so before live) | D4 ALTERED check, E1 to E3 bot | C4 proof drawer, D4 upload UI, card PNG template | forward real PNG → VERIFIED; edited PNG → ALTERED, 10 of 10 tries |
| **P4 During** | Oct 17 | live bridge | B2 to B6 (websocket relay, spotting, instant match, cold path), H2 benchmark runner | B1 capture, B7 live feed, F1 strings | demo clip: prebunked claim card in under 1.5 s; cold claim verdict shows |
| **P5 Ship** | Oct 18 | submit by 8 PM IST, not 11:59 | bugfix only, README + notices, benchmark numbers, 1024 char description draft | deck in prescribed template → PDF under 5 MB ✅, video under 3:00, submit form | all 4 links open in an incognito window; form submitted |

🔴 Feature freeze: **Oct 18, 12:00 noon IST**. After that only fixes. 🟡

## 2. Daily rhythm

- 10:00 IST: 10 min sync in LC DM, what merged, what's blocked.
- L posts PR plan → S okays → L raises PR → S merges + deploys. Target: max 2 open PRs at a time.
- 22:00 IST: deployed URL smoke test, one line status.

## 3. What Agent can and cannot do (honest)

| Can | Cannot |
|---|---|
| write backend, pipeline, bot, prompts, benchmark, docs, deploy scripts | touch your laptop or GCP console |
| raise PRs to your repo | deploy without you (unless you hand a deploy only service account key through a private drop link, never in chat) |
| debug from logs you share | record the video or present as a team member |
| research + test prompts quickly | guarantee model quality on Hinglish before day 1 tests |

## 4. Risks and fallbacks

| Risk | Level | Fallback |
|---|---|---|
| Live transcription poor on Hinglish | 🔴 | switch to Speech-to-Text; worst case clip upload path with full transcript |
| Tab audio capture flaky outside Chrome | 🟡 | demo in Chrome; clip upload |
| Grounding quota / latency | 🟡 | prebunk does the heavy calls before the demo; cache verdicts |
| ALTERED check misses edits after compression | 🔴 | text diff is primary (verdict word + claim), pHash is secondary; test with real Telegram forwards on Oct 16 |
| Prebunk predicts claims that are never said | 🟡 | pick a demo topic where claims recur; report hit rate honestly |
| Deploy breaks during evaluation (Oct 19 to Nov 6) | 🔴 | min instances 1, budget alert, no deploys after submit ✅ link must stay up |
| Team bandwidth | 🔴 | cut order in 07; Agent takes more backend, never frontend polish |

## 5. Submission checklist (✅ from your submission page file)

- [ ] Challenge: Media, Content & Digital Experiences
- [ ] Prototype link on Cloud Run / Firebase, works for 3 weeks
- [ ] Deck in the prescribed template, PDF, ≤ 5 MB
- [ ] Public GitHub repo
- [ ] Demo video, under 3:00 (page also says 3 to 4 min; the form says up to 3, so stay under 3)
- [ ] Description ≤ 1024 chars naming Firebase, Firestore, Cloud Run, Gemini
