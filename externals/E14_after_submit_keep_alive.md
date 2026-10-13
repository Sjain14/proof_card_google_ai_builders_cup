# E14 · After submit: keep the link alive

**Window:** 19 Oct to 6 Nov (evaluation) 🟡 per Cup timeline.

## Steps
1. Turn on branch protection "no pushes to main" or simply: no merges, no deploys after submit. A broken deploy during judging = zero.
2. Keep `--min-instances 1` on `proofcard-api` so the first judge click isn't a cold start.
3. Leave billing on; budget alert stays.
4. Once a week, open the live URL and run smoke test 4 from E09.

## Done when
Judging closes.
