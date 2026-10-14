# E11 results: real Telegram forward + ALTERED

Fill this in after E11, commit it in a PR (or paste in DM). Slide 12 of the deck quotes the pass count from this file (`DECK_TEXT.md`, `{{E11:pass_count}}`).

🔴 Screenshots: crop out phone numbers, names and other chats before adding them. This repo goes public. Save them as `externals/inputs/e11/<run>.png`.

## Setup

| Field | Value |
|---|---|
| Date + time (IST) | |
| Deployed URL | |
| Bot | @ |
| Commit sha on Cloud Run (Actions → deploy summary) | |
| Phone A (sharer): model, OS, Telegram version | |
| Phone B (forwarder): model, OS, Telegram version | |
| Send mode | photo (compressed) / file (uncompressed) |

## A. Forward an untouched card → expect VERIFIED (5 runs)

| Run | Card id | Path (share button → friend → forward to bot) | Bot said | "Open proof" opened `/v/:id`? | Correct? | Screenshot if wrong |
|---|---|---|---|---|---|---|
| A1 | | | | | | |
| A2 | | | | | | |
| A3 | | | | | | |
| A4 | | | | | | |
| A5 | | | | | | |

## B. Edited copy → expect ALTERED + what changed (5 runs)

Vary the edit: verdict word, a number in the claim, a source name, a crop, a colour change.

| Run | Card id | What you edited (tool + change) | Bot said | Did it name the edited part? | Correct? | Screenshot if wrong |
|---|---|---|---|---|---|---|
| B1 | | | | | | |
| B2 | | | | | | |
| B3 | | | | | | |
| B4 | | | | | | |
| B5 | | | | | | |

## C. Inline share

| Check | Result |
|---|---|
| `@<bot> ` in any chat lists cards | |
| Picking one posts the card with the proof button | |

## Total

**pass_count:** __ / 10 (A + B correct)

Anything odd (slow replies, wrong language, button missing):

## Filled in by Agent (do not edit)

| Failure | Cause found | Fix PR | Re test result |
|---|---|---|---|
| | | | |
