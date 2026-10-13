# 05 · UI / UX

Labels: ✅ verified · 🟡 design choice. UX is 10% of score ✅ [FAQ](https://aibuildercup.com/Faqs.html), so: clear over clever, zero heavy animation.

## 1. Principles

1. **Verdict first.** The verdict word is the biggest thing on every card. Readable in 1 second on a phone screenshot.
2. **Proof one tap away.** Every verdict has its source snippet one tap down, never a bare link.
3. **Speed is visible.** Show latency on live cards ("0.6 s · prebunked" vs "7.9 s · live check"). This is our Innovation proof on screen.
4. **Never blank, never fake.** Checking, failed, unverifiable all have honest states.
5. **Bilingual by default.** Claim shown in the language spoken; one line explanation in the same language; English toggle.
6. **Mobile first for /v/:id and Telegram**, desktop first for the admin Live screen (player + feed side by side).

## 2. Card anatomy (the hero component)

```
┌────────────────────────────────────────┐
│ FALSE                     PREBUNKED 0.6s│  ← verdict pill + badge
│ "Petrol is cheapest in India in Asia"  │  ← claim, quoted, ≤2 lines
│ Petrol in India costs more than in ... │  ← why, ≤2 lines
│ 2 sources · support 0.91               │
│ ▸ Proof                                │  ← drawer: snippet, hash, time
│ [Copy link] [Telegram] [PNG]   id: K7Q2│
└────────────────────────────────────────┘
```
(example claim is illustrative only, not a checked fact 🟡)

PNG version (for forwarding): 1080x1350, same layout, adds QR to `/v/<id>`, footer "Check this card: forward it to @<bot>". The id and QR are what makes the ALTERED check possible.

## 3. Verdict states

| State | Colour token | Icon | Copy |
|---|---|---|---|
| TRUE | `verdict-true` green | check | "True" / "सही" |
| MISLEADING | `verdict-mislead` amber | half circle | "Misleading" / "भ्रामक" |
| FALSE | `verdict-false` red | cross | "False" / "गलत" |
| UNVERIFIABLE | `verdict-unknown` grey | question | "Not enough proof" / "पुख्ता सबूत नहीं" |
| checking | grey shimmer | spinner | "Checking sources..." |
| ALTERED | red outline + stripe | warning | "This card was edited" |

Hindi strings: Team lead/native speaker to confirm wording 🟡.

## 4. Accessibility

- Verdict never colour only: always word + icon (colour blind safe) 🟡.
- Contrast ≥ 4.5:1 for text (WCAG AA) 🟡 standard.
- Devanagari font that renders well at small size (Noto Sans Devanagari, OFL licence 🟡 confirm).
- Live feed: `aria-live="polite"` on new cards.

## 5. Interaction details that score

| Detail | Why |
|---|---|
| New live card slides in at top, 150 ms, no bounce | feels instant without distraction |
| Prebunk hit flashes the matching card in the brief grid too | shows judges the "Before" paid off |
| Proof drawer highlights the exact sentence on the source | answers "source?" without leaving |
| ALTERED screen shows word diff (strike old, mark new) | judge sees exactly what was faked |
| Latency chip | numbers beat adjectives |

## 6. What NOT to build

3D hero, scroll animations, dark/light theme switcher, settings page, profile page, dashboards. Zero judge value in a 3 minute video 🟡.
