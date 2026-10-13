# Judging Criteria · the gate every phase and PR passes

Team lead, 13 Oct 21:59Z: "whatever we develop must satisfy the judging criteria". 22:00Z: "very high end, completely working and integrated, so we get selected for Singapore".

Labels: ✅ verified on the official page (read 13 Oct 23:3xZ UTC) · 🟡 inference / judgement.
Deck slides, submission text and per criterion scores live in [10_Criteria_Map_Deck_Submission.md](10_Criteria_Map_Deck_Submission.md). This file is the gate, not a copy of that one.

## 1. Official criteria ✅

Source: [aibuildercup.com FAQ](https://aibuildercup.com/Faqs.html), section Judging & Evaluation. The same four weighted criteria apply to all six themes.

| # | Criterion | Weight |
|---|---|---|
| C1 | Technical Merit & Gen AI Implementation | 40% |
| C2 | Problem Alignment & Impact | 25% |
| C3 | Innovation & Creativity | 25% |
| C4 | User Experience & Solution Design | 10% |

Hard requirements from the same FAQ ✅:
- A working prototype that functions **end to end** and is **deployed on Cloud Run / GCP / Firebase**.
- Built on the **Google Cloud** stack (other clouds are not evaluated).
- **Fresh project** built during the hackathon window.
- Team of 2 to 4, all **21+**, JAPAC based, **no students** (a student anywhere = whole team disqualified, even after shortlisting).

## 2. Road to Singapore ✅

Source: [aibuildercup.com](https://aibuildercup.com/) Timeline + FAQ.

| Stage | Date (2026) |
|---|---|
| Team formation closes | 14 Oct |
| Prototype submission deadline | 18 Oct |
| Evaluation (scoring round) | 19 Oct to 6 Nov |
| Finalists announced | 7 Nov |
| Grand Finale, Demo Day, Singapore (in person, live panel of Google Cloud and industry experts) | 4 Dec |

- There is a **scoring round before the finale**; it alone decides who travels ✅. So the submission (deployed link, video, deck) must win on its own, with no chance to explain live.
- Only **2 members** per shortlisted team travel ✅.

🟡 What that means for us: the evaluator likely spends minutes, not hours, per entry. Whatever is not visible in the video and on the deployed link in the first 60 seconds scores zero.

## 3. Criterion → what we build → phase → the demo moment that proves it

| # | What earns it | Phase | Demo moment (must be real, no mocks) |
|---|---|---|---|
| C1 | GenAI does 3 distinct jobs: predict claims (prebunk), grounded verify with sources, live semantic match; model never has the last word (D13); hashed source snapshots | P2 prebunk, P3 capsule, P5 live bridge | video 0:45 to 2:45: brief built, live stream claim matched in under a second (latency chip), cold claim verified live |
| C1 | Fully deployed and integrated on Google Cloud | P1 spine + every phase | deployed link opens on a phone; architecture slide matches what runs |
| C2 | Misinformation in forwarded video clips, Hindi / English / Hinglish, prebunking is evidence based (doc 10 §1) | P2, P4 | slide 3 and 4, video 0:25: a real Hinglish claim |
| C3 | Before + During + After in one flow; ALTERED check catches a one word edit after Telegram recompression | P3, P5 | video hook 0:00: forwarded card comes back ALTERED |
| C4 | One flow, verdict first cards, mobile verify page without login, bot | P4, P3 | `/v/:id` on a phone in under 30 seconds |

## 4. Finalist bar (gate for every phase)

A phase is done only when all of these hold:
1. **Works end to end** on the demo path with real services; emulators and fakes only inside tests ✅ (FAQ: end to end + deployed).
2. **Integrated**: the phase is reachable from the UI or the bot, not only from a script.
3. **Visible**: the phase adds a moment to the demo table above, or it does not ship before 18 Oct.
4. **Polished**: passes the design system in `05_UI_UX.md` and a separate design review on desktop and mobile.
5. **Gates green**: lint, strict types, tests, coverage, dependency audit, rules tests.

## 5. PR checklist (copied into every PR body and CHANGELOG entry)

```
### Judging criteria
- [ ] C1 Tech + GenAI (40%): what this PR moves, evidence
- [ ] C2 Impact (25%): what this PR moves, evidence
- [ ] C3 Innovation (25%): what this PR moves, evidence
- [ ] C4 UX (10%): what this PR moves, evidence
- [ ] Finalist bar §4: end to end, integrated, visible in demo, polished, gates green
```

The template is in `.github/pull_request_template.md`.
