# externals/ · everything only a human on the team can do

Agent keeps building and documenting without waiting. This folder is the full list of inputs, accounts, setups and decisions that need **you** (Team lead + team). Do them in one sitting, in order. Each file has exact steps and a "done when" line.

Labels: ✅ verified against the linked official doc · 🟡 estimate or plan.

🔴 Keys, tokens, passwords: never paste in chat, never commit. They go straight into Secret Manager (or GitHub encrypted secrets). If Agent ever needs one, Agent sends you a private one time drop link.

## Order (phase by phase, per `context/09_Dev_Plan_Phases.md`)

| # | File | Phase it unblocks | Deadline | Time 🟡 | Status |
|---|---|---|---|---|---|
| E01 | [E01_team_no_students.md](E01_team_no_students.md) | all (DQ risk) | **14 Oct**, team formation closes | 15 min | ☐ |
| E02 | [E02_lock_name_topic_clip.md](E02_lock_name_topic_clip.md) | P2 prebunk, P4 demo | 14 Oct | 20 min | ☐ |
| E03 | [E03_gcp_project_billing.md](E03_gcp_project_billing.md) | every deploy | 14 Oct | 15 min | ☐ |
| E04 | [E04_enable_apis.md](E04_enable_apis.md) | every deploy | 14 Oct | 10 min | ☐ |
| E05 | [E05_firebase_hosting_auth.md](E05_firebase_hosting_auth.md) | P2 frontend live | 14 Oct | 20 min | ☐ |
| E06 | [E06_service_accounts_iam.md](E06_service_accounts_iam.md) | P1 backend live | 14 Oct | 15 min | ☐ |
| E07 | [E07_telegram_bot_secrets.md](E07_telegram_bot_secrets.md) | P3 Proof Capsule bot | 15 Oct | 10 min | ☐ |
| E08 | [E08_github_ci_deploy_access.md](E08_github_ci_deploy_access.md) | auto deploy from CI | 15 Oct | 20 min | ☐ |
| E09 | [E09_first_deploy.md](E09_first_deploy.md) | P2 to P5 live URL | 15 Oct | 30 min | ☐ |
| E10 | [E10_console_checks_models_quota.md](E10_console_checks_models_quota.md) | P2 real model calls | 15 Oct | 20 min | ☐ |
| E11 | [E11_demo_dry_run_telegram_forward.md](E11_demo_dry_run_telegram_forward.md) | P3 exit test | 16 Oct | 20 min | ☐ |
| E12 | [E12_demo_video.md](E12_demo_video.md) | P5 submission | 18 Oct | 2 to 3 h | ☐ |
| E13 | [E13_deck_and_submission.md](E13_deck_and_submission.md) | P5 submission | **18 Oct, submit by 8 PM IST** | 2 h | ☐ |
| E14 | [E14_after_submit_keep_alive.md](E14_after_submit_keep_alive.md) | judging window | 19 Oct to 6 Nov | 5 min | ☐ |

## What works without you (so nothing is blocked)

Until E03 to E09 are done, everything runs locally against the Firestore emulator with a deterministic model stub (`PC_MODEL_MODE=stub`). The moment your project exists, the same code switches to Gemini on Vertex AI with `PC_MODEL_MODE=vertex` plus your project id. No code changes needed on your side.

Tick the box in this table (edit the file in GitHub) when you finish a step, and drop one line in DM. Agent reads this file before every PR.
