# 06 · Brand Guidelines (v0, hackathon grade)

All of this is a proposal 🟡. Team lead to lock or change the name and palette on Oct 14; everything else follows.

## 1. Name

**Proof Card** (working name). Tagline options:
1. "Know the claim before it's said."
2. "Proof that travels."
3. "Check before you forward." (Hindi: "फॉरवर्ड से पहले जाँचो")

🟡 Do a 5 minute name check on Oct 14 (GitHub, Telegram bot username availability, domain not required since Firebase gives `*.web.app`).

## 2. Personality

Calm, factual, fast. Not preachy, not partisan, never mocking the speaker. We judge claims, not people. 🟡 Important for Impact judges and for using real political clips.

## 3. Voice rules

| Do | Don't |
|---|---|
| "False. RBI data shows X." | "Totally fake news!!" |
| Short, plain, bilingual | jargon ("LLM", "RAG") on user screens |
| Say "not enough proof" when unsure | force a TRUE/FALSE |

## 4. Colour

| Token | Hex | Use |
|---|---|---|
| ink | `#111827` | text |
| paper | `#FAFAF7` | background |
| brand | `#1F4FFF` | buttons, links, logo |
| verdict-true | `#15803D` | TRUE |
| verdict-mislead | `#B45309` | MISLEADING |
| verdict-false | `#B91C1C` | FALSE, ALTERED |
| verdict-unknown | `#6B7280` | UNVERIFIABLE |

Check contrast of each on paper before using for text 🟡.

## 5. Type

- UI + Latin: Inter. Devanagari: Noto Sans Devanagari. Both OFL licensed 🟡 confirm.
- Verdict word: 700 weight, uppercase, letter spacing 0.04em.

## 6. Logo

A card outline with a check mark cut into the corner (proof stamp). Flat, one colour, works at 32 px for the Telegram bot avatar. 🟡 Make it in 30 minutes in Figma or SVG by hand; don't spend more.

## 7. Assets needed (owner: Team lead, frontend)

| Asset | Size |
|---|---|
| Bot avatar | 512x512 PNG |
| Favicon | 32, 192, 512 |
| OG image for `/v/:id` | 1200x630 (auto rendered per card) |
| Card PNG template | 1080x1350 |
| Deck theme | use the prescribed Hack2skill template, only swap accent colour ✅ template is mandatory per submission page |
