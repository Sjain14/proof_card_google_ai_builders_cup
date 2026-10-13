# 10 · Criteria Map, Deck Slide Map, Submission Text

Labels: ✅ verified · 🟡 inference / judgement. Scores carried from the verdict doc (sent 13 Oct): as is 5.2/10, narrowed 7.4/10 🟡.

## 1. Every criterion → what earns it → which doc → proof on screen

✅ Criteria and weights: [aibuildercup.com FAQ](https://aibuildercup.com/Faqs.html), same for all themes.

| Criterion | Weight | What earns points here | Built by (07 ids) | Shown where | Narrowed score 🟡 |
|---|---|---|---|---|---|
| Technical Merit & Gen AI Implementation | 40% | GenAI does 3 distinct jobs (predict claims, grounded verify, live semantic match) + faithfulness gate + integrity hashing + isolated fetcher; working deploy; latency numbers | A2 A3 A4 A5 B3 B5 C1 to C3 D4 | video 0:45 to 2:45, slides 8, 9, 12 | 8 |
| Problem Alignment & Impact | 25% | track lists "misinformation analysis" ✅ (your track screenshot); Hindi/Hinglish; forward stage; prebunking evidence ✅ [Science Advances](https://www.science.org/doi/10.1126/sciadv.abo6254) | F1 D E | slides 3, 4, video 0:25 | 7 |
| Innovation & Creativity | 25% | Before + After combo none of the 5 competitors show (08 §5); ALTERED check; instant card from prebunk | A, B5, D4, E2 | video hook 0:00, slide 4 | 7 |
| User Experience & Solution Design | 10% | one flow, verdict first cards, latency chip, mobile verify page, bot | A6 B7 C4 D2 | slides 6, 7, 11 | 7 |

🔴 Hard truth: theme fit gives zero edge here because the track itself suggests misinformation, so many entries will be fact checkers 🟡. Points come from Tech depth and the Before + After demo, nothing else.

## 2. Deck: prescribed template slide by slide (✅ template you shared, 14 content slides)

| Slide | Template title | What we put |
|---|---|---|
| 1 | Team Details | team name, leader, "Media, Content & Digital Experiences" |
| 3 | Brief about the idea | the one line + 3 step Before / During / After graphic |
| 4 | Opportunities (how different, how it solves, USP) | competitor gap table from 08 §5; USP = "proof that survives the forward" |
| 5 | List of features | 07 groups A to E, one line each, PREBUNKED and ALTERED highlighted |
| 6 | Process flow / use case | user flow from 04 §2 |
| 7 | Wireframes (optional) | screenshots of S3, S4, S5, bot |
| 8 | Architecture | diagram from 03 §1 |
| 9 | Technologies | Google list from 02 + open source line |
| 10 | Implementation cost (optional) | per 1,000 checks estimate from real Cloud Billing numbers after Oct 17 🟡, else skip |
| 11 | Snapshots of the prototype | 4 real screenshots |
| 12 | Performance / benchmarking | H2 results: accuracy, prebunked vs cold latency, tamper detection rate |
| 13 | Future development | Pravachan mode, WhatsApp, extension, newsroom API |
| 14 | Links | repo, video, deployed link |

Note: slide 2 is the template's own instruction slide; delete it before export 🟡.

## 3. Brief description draft (submission form, ≤ 1024 chars, must name Firebase, Firestore, Cloud Run, Gemini ✅)

> Proof Card fights misinformation before, during and after a video. Before a stream, Gemini on Vertex AI predicts the claims a topic or speaker is likely to make and verifies each with Google Search grounding and the Fact Check Tools API, scored by Vertex check grounding. During playback, live audio is transcribed, claims are spotted and matched to the pre verified set with Firestore vector search, so verdicts appear instantly; new claims are checked live. After, every verdict becomes a Proof Card: a public verify link with the exact source snippet and a sha256 hashed snapshot in Cloud Storage. Forward a card to our Telegram bot and it tells you if the copy was ALTERED. Works in Hindi, English and Hinglish. Built on Cloud Run (API and an isolated fetcher), Cloud Tasks, Firestore, Cloud Storage, Firebase Hosting, Auth and App Check, with EmbeddingGemma for embeddings.

(878 chars, counted; recount after edits; edit once features are real, never claim what isn't deployed.)

## 4. Pre submit self check (score it like a judge would)

| Question a judge asks | Answer must be on screen |
|---|---|
| Is GenAI doing real work or just a chatbot? | 3 jobs + support score visible |
| Does it actually work? | real recording, deployed link opens |
| What's new vs existing tools? | slide 4 table + the ALTERED moment |
| Who uses it, why care? | admin persona, Hindi/Hinglish, forward problem |
| Can I use it in 30 seconds? | `/v/:id` on a phone, no login |
