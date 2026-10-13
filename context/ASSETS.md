# Assets · source and licence for everything we ship

Rule (Team lead, 13 Oct 22:02Z, AGENTS.md §0): assets may come from the internet only under a licence that allows use, credited here. One row per asset, added in the same PR that adds the asset.

| Asset | Source | Licence | Where used |
|---|---|---|---|
| Inter (variable) | [@fontsource-variable/inter 5.3.0](https://fontsource.org/fonts/inter) | SIL OFL 1.1 | frontend brand font, self hosted |
| Noto Sans (subset Latin, 400 to 700) | [Google Fonts, Noto Sans](https://fonts.google.com/noto/specimen/Noto+Sans) | SIL OFL 1.1 (`backend/app/assets/fonts/OFL.txt`) | Proof Card image render (`card_image.py`) |
| Noto Sans Devanagari (subset) | [Google Fonts, Noto Sans Devanagari](https://fonts.google.com/noto/specimen/Noto+Sans+Devanagari) | SIL OFL 1.1 (`backend/app/assets/fonts/OFL.txt`) | Hindi text on the Proof Card image |
| `favicon.svg`, verdict icons, inline SVG marks | made in this repo | same as repo | frontend header, cards, share page |

No photos or stock images ship yet. Allowed sources when they do: Unsplash (Unsplash Licence), Pexels (Pexels Licence), icon sets under MIT / ISC, fonts under OFL. Never: images found via search with no licence, logos of real news outlets or people without permission.

Animations are code (CSS / Web Animations API), not downloaded assets; they follow the motion timings in `05_UI_UX.md` and respect `prefers-reduced-motion`.
