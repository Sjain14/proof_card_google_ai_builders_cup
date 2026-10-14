# Demo video script (E12): Hinglish voice over + English captions

Labels: ✅ verified · 🟡 inference / judgement.
Length **2:57**, under the 3:00 form limit ✅ (E12). Beats from `externals/E12_demo_video.md`. Captions: [captions_en.srt](captions_en.srt) (same cue numbers and times as this table). Upload the `.srt` in YouTube Studio → Subtitles → English → Upload file → With timing.

## Rules
- 🔴 Record the real system. Every card, latency chip and bot reply on screen comes from the deployed link (04 §5: a staged demo kills the Tech score 🟡).
- A team member voices it (judges must hear the team). Read the VO column as written; the Roman Hinglish is for reading aloud.
- Cue 15 is written in the masculine ("bhejta hoon"); a female voice reads "bhejti hoon", and the caption stays the same.
- `{{...}}` placeholders are filled from real runs **before** recording, in both this file and the `.srt`: `BRIEF_N` = claims ready on the brief you record, `MATCH_MS` = the PREBUNKED chip on screen (and `live.match_p50_ms` from the bench file for cue 21), `COLD_S` = the cold card's latency on screen, `ACC` = `overall.accuracy`, `TAMPER` = `tamper.edit_caught_rate`. Numbers spoken must match numbers on screen.
- If a measured number is weak, say the true number or cut the cue. Never round up.
- Pace: max 2.9 words per second in any cue (last column) 🟡; natural Hinglish speech runs about 2.5. If a take runs long, cut cue 11 first, then cue 22.
- Fallback for "During": if tab audio is weak on the clip, use the clip upload path (PR #21) and change cue 9 to "Ab clip. Recording upload karte hi har line jaanchi jaati hai." / "Now a clip. Upload the recording and every line gets checked."

## Script

| # | Time | Beat | Screen | VO (Hinglish, spoken) | Caption (English) | words/s |
|---|---|---|---|---|---|---|
| 1 | 0:00.0 to 0:04.0 | Problem | Phone: a forwarded fake screenshot in a family group | Ye message aapke family group mein bhi aaya hoga. | You've probably seen this message in your family group. | 2.2 |
| 2 | 0:04.0 to 0:09.0 | Problem | Zoom on the screenshot: speech photo + one number | Ek bhashan ka screenshot, ek number, aur ek jhooth jo sach jaisa lagta hai. | A screenshot of a speech, one number, and a lie that looks true. | 2.8 |
| 3 | 0:09.0 to 0:15.0 | Problem | Landing page, headline | Fact check aata hai, par tab tak forward ho chuka hota hai. Proof Card ulta chalta hai. | The fact check comes, but by then it has been forwarded. Proof Card works the other way round. | 2.8 |
| 4 | 0:15.0 to 0:20.0 | Before | New brief: type topic + speaker (from demo_claims.md) | Bhashan se pehle, hum sirf topic aur speaker daalte hain. | Before the speech, we just enter the topic and the speaker. | 2.0 |
| 5 | 0:20.0 to 0:27.0 | Before | Brief page: claims appear one by one | Gemini aane wale dawon ka andaza lagata hai, aur har dawa Google Search se jaanchta hai. | Gemini predicts the claims that are coming and checks each one with Google Search. | 2.3 |
| 6 | 0:27.0 to 0:35.0 | Before | Open one card: source line highlighted, sha256 | Par aakhri faisla model ka nahi. Har source page hum khud kholte hain, wahi line dhoondhte hain, aur page ka hash rakhte hain. | But the model never has the last word. We open every source page ourselves, find the exact line, and keep a hash of the page. | 2.9 |
| 7 | 0:35.0 to 0:42.0 | Before | A card that says Not enough proof | Line nahi mili, to card saaf bolta hai: pukhta saboot nahi. Zabardasti sahi ya galat nahi. | No line, and the card says it plainly: not enough proof. No forced true or false. | 2.3 |
| 8 | 0:42.0 to 0:50.0 | Before | Progress bar full, Go live button | Speech shuru hone se pehle, {{BRIEF_N}} dawe sources ke saath taiyaar. | Before the speech starts, {{BRIEF_N}} claims are ready, with sources. | 1.4 |
| 9 | 0:50.0 to 0:56.0 | During | Live page: player, Start listening, share tab audio | Ab live. Video isi tab mein chalta hai, Proof Card sirf yahi tab sunta hai. | Now live. The video plays in this tab, and Proof Card listens to this tab only. | 2.5 |
| 10 | 0:56.0 to 1:04.0 | During | Claim from demo_claims.md is spoken, PREBUNKED card pops, ms chip | Speaker ne wahi dawa bola jo brief mein tha... aur card turant aa gaya. PREBUNKED, {{MATCH_MS}} milliseconds. | The speaker says a claim from the brief... and the card is already there. PREBUNKED, in {{MATCH_MS}} milliseconds. | 2.1 |
| 11 | 1:04.0 to 1:12.0 | During | Heard line under the player, card in the feed | Gemini sunke transcribe karta hai, dawa pakadta hai, aur embeddings se brief ke dawe se milata hai. Hindi, English, Hinglish, teeno. | Gemini transcribes, spots the claim and matches it to the brief with embeddings. Hindi, English and Hinglish. | 2.6 |
| 12 | 1:12.0 to 1:22.0 | During | The cold claim: LIVE badge, Checking sources | Aur ye naya dawa? Brief mein nahi tha. Ye live jaancha ja raha hai, wahi raasta, wahi saboot. | And this new claim? It wasn't in the brief. It gets checked live: same path, same proof. | 1.8 |
| 13 | 1:22.0 to 1:30.0 | During | Cold card lands with verdict + source line | {{COLD_S}} second mein verdict, source ki line ke saath. | A verdict in {{COLD_S}} seconds, with the source line. | 1.1 |
| 14 | 1:30.0 to 1:37.0 | After | Card image full screen: verdict, QR, id | Ab asli kaam. Har verdict ek Proof Card hai, QR aur fingerprint ke saath. | Now the real job. Every verdict is a Proof Card, with a QR and a fingerprint. | 2.0 |
| 15 | 1:37.0 to 1:44.0 | After | Phone A: Share to Telegram, Phone B: forward to the bot | Main ise Telegram pe bhejta hoon. Dost ise hamare bot ko forward karta hai. | I share it on Telegram. My friend forwards it to our bot. | 2.0 |
| 16 | 1:44.0 to 1:52.0 | After | Bot replies VERIFIED, tap Open proof, /v/:id opens | VERIFIED. Telegram ne image compress ki, phir bhi card pehchana gaya. Ek tap, aur poora saboot khulta hai. | VERIFIED. Telegram compressed the image, and the card is still recognised. One tap opens the full proof. | 2.2 |
| 17 | 1:52.0 to 2:02.0 | After | Photo editor: change FALSE to TRUE (or a number), send to the bot | Ab koi isme ek shabd badal de. Galat ko sahi kar de, aur aage forward kare. | Now someone changes one word. Turns FALSE into TRUE, and forwards it on. | 1.6 |
| 18 | 2:02.0 to 2:12.0 | After | Bot replies ALTERED, names the edited part, shows the original | ALTERED. Bot batata hai kya badla, aur asli card dikhata hai. | ALTERED. The bot shows what was changed, and the original card. | 1.1 |
| 19 | 2:12.0 to 2:20.0 | After | /v/:id on a phone, no login, sources + hash | Bina login ke, kisi bhi phone pe. Saboot forward ke saath chalta hai. | No login, on any phone. The proof travels with the forward. | 1.6 |
| 20 | 2:20.0 to 2:30.0 | Stack | Architecture slide (DECK_TEXT.md slide 8) | Bana hai Vertex AI pe Gemini aur Google Search grounding se, Cloud Run, Cloud Tasks, Firestore, Cloud Storage aur Firebase pe. | Built with Gemini on Vertex AI and Google Search grounding, on Cloud Run, Cloud Tasks, Firestore, Cloud Storage and Firebase. | 2.1 |
| 21 | 2:30.0 to 2:40.0 | Numbers | Benchmark slide (DECK_TEXT.md slide 12) | Pachaas dawon ke benchmark pe: accuracy {{ACC}}, prebunked card {{MATCH_MS}} milliseconds mein, aur edit pakde gaye {{TAMPER}}. | On a 50 claim benchmark: accuracy {{ACC}}, prebunked cards in {{MATCH_MS}} ms, edits caught {{TAMPER}}. | 1.7 |
| 22 | 2:40.0 to 2:50.0 | Numbers | Repo: backend/bench/results/<date>.json | Har number repo mein committed result file se aata hai. | Every number comes from a result file committed in the repo. | 1.0 |
| 23 | 2:50.0 to 2:57.0 | Close | Logo + prototype URL | Proof Card. Dawa bole jaane se pehle jaaniye. | Proof Card. Know the claim before it's said. | 1.1 |

## Recording checklist
1. Demo topic, clip and claims from `externals/inputs/demo_claims.md`, dry run done by Agent first.
2. 1080p, Chrome clean profile, zoom 110 %, notifications off, no personal chats visible on either phone.
3. Record screen first, VO after, lay the VO on the cue times; nudge cues in the `.srt` if the edit shifts.
4. Export MP4, YouTube Unlisted, captions uploaded, open logged out in incognito, check length under 3:00.
