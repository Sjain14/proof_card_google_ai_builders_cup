# 01 · PRD: Proof Card

Version 1 · 13 Oct 2026 · Scope = NARROWED (locked in chat 13 Oct, 21:28Z)
Labels: ✅ verified from linked source · 🟡 our inference / judgement

## 1. One line

Proof Card checks the claims a stream is likely to make **before** it starts, shows the verdict the **same second** the claim is spoken, and turns every verdict into a **tamper evident proof card** that says ALTERED if anyone edits a forwarded copy.

## 2. Problem

- Misinformation in India spreads by forward, in Hindi, English and Hinglish, long after the video ends. 🟡 (our framing; WhatsApp dominance in India ✅ [Sinch](https://sinch.com/blog/messaging-apps-in-india/))
- Live fact checkers react after the claim is said, take seconds per claim, and their output dies inside the app (InTruth exports a private PDF ✅ [session-export.js](https://github.com/rpanigrahi222/intruth-factcheck/blob/master/realtime-factcheck/src/content/session-export.js)).
- Fact check screenshots themselves get edited and reforwarded. Nobody can tell a real card from a doctored one. 🟡 (no competitor in our scan offers a tamper check ✅ see 08_Reuse_Map competitor table)
- Prebunking works: inoculation videos improved resilience at YouTube scale ✅ [Science Advances 2022](https://www.science.org/doi/10.1126/sciadv.abo6254). But today it is human led (Full Fact briefs) and slow. 🟡

## 3. Users (pick ONE for the demo)

| User | Job to be done | Primary? |
|---|---|---|
| **Community / group admin** (family, society, community Telegram/WhatsApp groups) | "Before tonight's debate, give me the likely false claims with proof, and let me check any card someone forwards" | ✅ primary 🟡 |
| Stream host / small news creator | "Show verified context on screen while I go live" | secondary |
| Viewer | "Is this forwarded card real?" | gets value through the verify link, no login |

🟡 Why the admin: the judge instantly gets the full loop (prepare, watch, share, catch the edit) and it matches where misinformation actually spreads.

## 4. Goals and non goals

**Goals (by 18 Oct 11:59 PM IST)**
1. Prebunk Brief: topic in, 10 to 15 predicted claims out, each with verdict + sources + proof snapshot.
2. Live bridge: a pasted YouTube link plays in our page; spoken claims that match a prebunked claim pop instantly; unmatched claims show "checking" then a verdict.
3. Proof Capsule: every card has `/v/<id>`, a PNG with id + QR, a sha256 hashed source snapshot, and an ALTERED check on edited copies.
4. Telegram bot: forward a card image → "verified" or "ALTERED" + Open proof button.
5. Benchmark: 50 Hindi/Hinglish/English claims, accuracy + latency (prebunked vs cold).

**Non goals (cut, roadmap slide only)**: Pravachan / scripture mode, browser extension, server side YouTube caption scraping, MCP, A2UI, BigQuery dashboards, session PDF export, multi platform capture, speaker diarization, WhatsApp Business API.

## 5. Functional requirements (short; full list in 07)

| ID | Requirement | Must |
|---|---|---|
| R1 | Generate predicted claims from topic + optional speaker + optional context links | 🔴 |
| R2 | Verify each claim with Gemini + Google Search grounding; store verdict, sources, support score | 🔴 |
| R3 | Fetch cited page in an isolated fetcher, find the quoted snippet, store snapshot + sha256 | 🔴 |
| R4 | Embed claims; match live sentences by vector search (Firestore `find_nearest`) | 🔴 |
| R5 | Live audio from the user's tab (getDisplayMedia) or uploaded clip → transcript → claim spotting | 🔴 |
| R6 | Card page `/v/<id>` publicly readable without login | 🔴 |
| R7 | ALTERED check: compare a submitted image/text to the canonical card | 🔴 |
| R8 | Telegram bot: photo in → verdict out, deep link `?start=<id>`, inline buttons | 🔴 |
| R9 | Hinglish handled in prompts end to end | 🟡 |
| R10 | Benchmark script + results file in repo | 🔴 |

## 6. Non functional

- Instant card (prebunk hit) p50 under 1.5 s from end of sentence 🟡 target, measure on Oct 17.
- Cold check p50 under 10 s 🟡 target.
- Prototype must stay up through evaluation (Oct 19 to Nov 6) ✅ submission rules page (your file "submissio page.pdf"): "The prototype must remain functional throughout the evaluation process", no retries. So: min instances 1 on the main service during evaluation, budget alerts on.
- Security: no keys in browser, untrusted URLs only fetched by a no permission service, prompt injection guard on fetched pages.

## 7. Success metrics (what goes on the deck)

| Metric | Target 🟡 |
|---|---|
| Verdict accuracy on 50 claim benchmark | report honestly, whatever it is |
| Prebunk hit rate (predicted claims actually said in the demo clip) | report honestly |
| Latency: prebunked vs cold | show the gap, this is the Innovation proof |
| Tamper detection on 20 edited cards | report detected / missed |

## 8. Criteria fit (from 10_Criteria_Map)

Tech + GenAI 40: GenAI does three different jobs (predict, verify, match) + faithfulness gate + integrity hashing. Impact 25: Hindi/Hinglish, forward stage. Innovation 25: Before + After, nobody in our scan has both. UX 10: one flow, three screens.

## 9. Open questions (need Team lead)

1. Team names + confirmation that nobody is a student (DQ rule ✅ [FAQ](https://aibuildercup.com/Faqs.html)). Team formation closes **14 Oct**.
2. Demo topic for the prebunk (pick something with checkable numbers, avoid religion and live elections 🟡).
3. Video length: the submission page says 3 to 4 min but the form field says "up to 3 minutes" ✅ (your submission page file). Plan for **under 3:00** to be safe.
