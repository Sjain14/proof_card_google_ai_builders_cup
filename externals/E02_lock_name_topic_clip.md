# E02 · Lock product name, demo topic, demo clip

**Deadline:** 14 Oct · **Unblocks:** P2 prebunk claim set, P4 live demo, benchmark numbers.

Working name in code is **Proof Card**. It is NOT one config line: it is drawn in `backend/app/card_image.py` and written in `frontend/index.html` + `frontend/src/i18n.ts` (there is no `brand.ts` / `PC_BRAND_NAME`). Keep **Proof Card**; a rename after cards exist breaks their ALTERED check.

## Steps
1. **Name.** Pick one. Check the .com / .in quickly and search GitHub + Product Hunt for clashes. Default if you don't pick: Proof Card.
2. **Demo topic.** Pick a topic where checkable numeric claims recur, so prebunk hits are likely. Good: budget / economy speech, fuel prices, a public health stat explainer. Avoid: religion, a live election, anything about a named private person (judging + safety risk 🟡).
3. **Demo clip.** 2 to 4 minutes, Hinglish or Hindi, a real public video with at least 5 numeric claims. Download it yourself (you own the copy for the demo; use a clip you are allowed to show). Save as `demo.mp4`.
4. Write down 5 claims from the clip you expect the system to catch (timestamp + exact words). This becomes the honest benchmark ground truth.
5. Put the clip somewhere private (Drive) and share the link only with the team. Do **not** commit the video to the public repo.

## What to hand Agent
One DM line: name, topic, clip link, and the 5 claims with timestamps (or fill the template `externals/inputs/demo_claims.md`).

## Done when
Name, topic and clip locked. Until then Agent builds against a sample topic ("India fuel prices 2026") in `backend/app/fixtures/`.
