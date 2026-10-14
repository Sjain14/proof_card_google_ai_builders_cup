# Demo claims (E02, step 4)

Fill this in, commit it in a PR (or paste the table in DM). This file is the honest ground truth for the demo: the video only shows hits on claims listed here, and Agent runs the clip against them before recording (E12).

🔴 Never commit the clip itself. Link it from Drive, shared with the team only. This repo goes public.

## Lock

| Field | Value |
|---|---|
| Product name | Proof Card |
| Demo topic (exact text typed into New brief) | |
| Speaker (as typed) | |
| YouTube link (public video, used in the player) | |
| Clip (Drive link, team only) | |
| Clip length (mm:ss) | |
| Language | Hindi / Hinglish / English |
| Right to show it in the demo | yes / source + licence: |

## Claims you expect the system to catch (at least 5)

Timestamps from the clip. Exact words as spoken, in the script they were spoken (Devanagari or Roman). Expected verdict only if you checked it yourself, with the source you used; otherwise leave it empty and Agent fills it from a sourced check, marked as such.

| # | Timestamp (mm:ss) | Exact words spoken | Has a number? | Expected verdict (TRUE / FALSE / MISLEADING / ?) | Your source (link) |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |
| 6 (optional) | | | | | |
| 7 (optional) | | | | | |

## One cold claim for the "checked live" beat

A claim that is NOT likely to be predicted from the topic alone, so the video shows the live path honestly.

| Timestamp | Exact words | Why it won't be in the brief |
|---|---|---|
| | | |

## Filled in by Agent after the dry run (do not edit)

| # | In the brief? (claim id) | Live result (PREBUNKED / LIVE / missed) | Similarity | Latency ms | Verdict on card | Notes |
|---|---|---|---|---|---|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |
| 4 | | | | | | |
| 5 | | | | | | |

Run: date, commit sha, path used (tab audio / clip upload), match threshold.
