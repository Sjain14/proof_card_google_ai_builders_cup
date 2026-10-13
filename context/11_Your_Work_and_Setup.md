# 11 · Your Work + Setup (Team lead and team)

Everything you need to do, in order. Agent can't do these from his side. Labels: ✅ verified · 🟡 estimate.

## Tonight / Oct 14 morning (~2.5 h total 🟡)

| # | Task | Time | Done when |
|---|---|---|---|
| 1 | Final team on Hack2skill, every member confirmed **not a student**, all 21+ and JAPAC based ✅ [FAQ](https://aibuildercup.com/Faqs.html). Formation closes **Oct 14** | 15 min | team page shows final members |
| 2 | Lock name, demo topic, demo clip (2 to 4 min, Hinglish, numeric claims, no religion / live election) | 20 min | one line in DM |
| 3 | Create public GitHub repo **on Oct 14** (fresh project rule ✅), add the agent account as collaborator, branch protection on `main` | 10 min | invite sent |
| 4 | GCP project (or the Cup credits project if they gave one), billing on, budget alert at a low amount | 15 min | alert email set |
| 5 | Enable APIs: Vertex AI, Cloud Run, Cloud Build, Cloud Tasks, Firestore (Native), Cloud Storage, Secret Manager, Fact Check Tools, Speech-to-Text, Discovery Engine (check grounding) 🟡 exact API names in console | 15 min | all show "enabled" |
| 6 | Firebase: add project, enable Hosting, Auth (Google + Anonymous), App Check | 20 min | `firebase init` done in repo |
| 7 | Service accounts: `api-sa` (Vertex user, Firestore user, Storage object admin, Tasks enqueuer, Secret accessor), `fetcher-sa` (no roles) | 15 min | both exist |
| 8 | Telegram: BotFather → `/newbot` → token **straight into Secret Manager** as `TG_BOT_TOKEN`; also create `TG_WEBHOOK_SECRET` (random string) | 10 min | secrets exist, token never pasted anywhere |
| 9 | Console checks from 02 §"Confirm in console": model ids in region, check grounding quota, Live transcription on 2 min of demo clip | 30 min | screenshot or one line each |

## How we pass code and deploys

- Agent posts the plan for each PR in DM → you ok → Agent raises PR → you review, merge, deploy (your PR rule stays).
- Deploy: `gcloud run deploy` commands + `firebase deploy` will be in `deploy/README.md`; you run them.
- Optional speed up: a deploy only service account key handed through a private drop link Agent sends you, never pasted in chat. Your call.

## Your build work (from 07, ~51 h must 🟡)

| Day | Your part |
|---|---|
| Oct 14 | steps above + Vite React app skeleton, Auth, Hosting rewrite to Cloud Run |
| Oct 15 | New Brief form (A1), Brief page with Firestore listener (A6), `/v/:id` styling (D2) |
| Oct 16 | Proof drawer (C4), "check a forwarded copy" upload (D4 UI), card PNG template + brand assets |
| Oct 17 | YouTube player + tab audio capture (B1), live feed (B7), Hindi/Hinglish strings (F1) |
| Oct 18 | deck in the template → PDF ≤ 5 MB, video under 3:00, description, submit by 8 PM IST |

## Things only humans can do

Record the video, voice over, present at finale, register / submit on Hack2skill, accept the terms, keep the deployed link alive Oct 19 to Nov 6 (no risky deploys after submit).
