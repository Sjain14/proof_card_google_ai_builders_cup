# E11 · Real device test: Telegram forward + ALTERED

**Deadline:** 16 Oct (P3 exit test) · **Needs:** E09.

Telegram recompresses photos, so the byte hash of a forwarded card never matches. The ALTERED check therefore relies on the card id in the QR + the text on the card + a perceptual hash (see `context/DECISIONS.md`). Only a real phone forward proves it.

## Steps (two phones, two Telegram accounts)
1. Create a brief, open any card, tap **Share to Telegram**, send it to a friend.
2. Friend forwards it to `@<yourbot>` → expect **VERIFIED** with an "Open proof" button.
3. Edit the card image (change the verdict word or a number in any photo editor), send the edited image to the bot → expect **ALTERED** and what changed.
4. Repeat each 5 times (10 total). Note any wrong result with a screenshot.
5. Try inline: in any chat type `@<yourbot> ` and pick a card.

## What to hand Agent
Pass count out of 10 and screenshots of any failures, in DM or `externals/inputs/e11_results.md`.

## Done when
10 of 10 correct, or failures reported so Agent can tune thresholds.
