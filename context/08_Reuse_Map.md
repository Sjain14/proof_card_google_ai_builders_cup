# 08 · Reuse Map: whose logic we use, how, and what we never copy

Labels: ✅ verified (GitHub API / page opened 13 Oct 2026) · 🟡 inference. Not legal advice.

## 1. Two rules that override everything

1. ✅ "Only fresh projects built during the hackathon timeline are eligible" ([FAQ](https://aibuildercup.com/Faqs.html)). So: **our code is written from Oct 14**. Open source libraries as dependencies are normal practice 🟡; copying another app's code wholesale is not.
2. Licence decides how we touch code:

| Licence | What we do |
|---|---|
| MIT, Apache-2.0, BSD | use as dependency, or adapt small pieces with the licence notice kept in `THIRD_PARTY_NOTICES.md` |
| LGPL | dependency only, never paste code |
| GPL / AGPL | read for ideas, never copy, never link into our service |
| custom, non commercial, no licence | read for ideas only, credit as inspiration, zero code |

## 2. Libraries we depend on

| Need | Repo | Licence | Stars / last push | How we use it |
|---|---|---|---|---|
| Claim spans from transcript | [google/langextract](https://github.com/google/langextract) | ✅ Apache-2.0 | 38.9k / 12 Oct 2026 | dependency in B4 |
| Clean page text | [adbar/trafilatura](https://github.com/adbar/trafilatura) | ✅ Apache-2.0 | 7.0k / 6 Oct 2026 | dependency in C2 |
| Fuzzy snippet locate | [rapidfuzz/RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | ✅ MIT | 4.2k / 12 Oct 2026 | dependency in C2 |
| Perceptual image hash | [JohannesBuchner/imagehash](https://github.com/JohannesBuchner/imagehash) | ✅ BSD-2-Clause | 3.9k / 12 Oct 2026 | dependency in D3, D4 |
| Agent conventions (optional) | [google/adk-python](https://github.com/google/adk-python) | ✅ Apache-2.0 | 21.8k / 13 Oct 2026 | only if time; plain pipeline first |
| Grounding examples | [google-gemini/cookbook](https://github.com/google-gemini/cookbook) | ✅ Apache-2.0 (feature research md) | | read patterns, write our own prompts |
| Card image + QR | Pillow, qrcode | 🟡 permissive, confirm on Oct 14 | | dependency in D3 |

## 3. Projects we learn from but never copy

| Project | Licence | What we learn | What we must NOT do |
|---|---|---|---|
| [InTruth](https://github.com/rpanigrahi222/intruth-factcheck) | ✅ custom, non commercial, credit required | verdict label set, claim pipeline order, source bias idea | copy any file; even a "port" risks DQ under fresh project rule 🟡 |
| [alandaitch/live-fact-checker](https://github.com/alandaitch/live-fact-checker) | ✅ MIT | how they wire Gemini + Search grounding for live checks; their failure modes | copy their app; MIT would allow it legally, but the Cup wants a fresh build and it's their core 🟡 |
| ClaimBuster ([utaresearch/claimbuster-spotter](https://github.com/utaresearch/claimbuster-spotter)) | ✅ GPL-3.0 (feature research md) | check worthiness idea for B4 | any code |
| Full Fact AI | product, closed | prebunk brief concept (human led) | n/a; cite as prior art |
| Duke Squash | shut | matching only works with an existing fact check pool; why we pre verify instead | n/a |
| youtube-transcript-api | ✅ MIT | | do **not** use server side: YouTube blocks cloud IPs ✅ [#415](https://github.com/jdepoix/youtube-transcript-api/issues/415) |

## 4. Where each reused piece plugs in

```
Brief ──A2 Gemini──► claims ──A3 FactCheck API / Search grounding──► verdict
                                      │
                                      ▼
            C1 fetcher ──► trafilatura ──► RapidFuzz ──► snapshot + sha256 (GCS)
                                      │
                                      ▼
                        D3 Pillow + qrcode ──► PNG ──► imagehash pHash
Live audio ──B3 Gemini Live──► text ──B4 langextract──► B5 Firestore find_nearest
Forwarded PNG ──E2 bot──► D4 QR id + Gemini vision text ──► diff + imagehash ──► VERIFIED / ALTERED
```

## 5. Competitor gap table (for the deck)

| Capability | InTruth | live-fact-checker | Devpost Veritas / VeriFact | **Proof Card** |
|---|---|---|---|---|
| Live claim check | ✅ | ✅ | ❌ paste a claim | ✅ thin |
| Pre verified brief before the stream | ❌ | ❌ | ❌ | ✅ |
| Instant card from prebunk match | ❌ | ❌ | ❌ | ✅ |
| Source snippet + hashed snapshot | ❌ 🟡 not found | ❌ 🟡 | 🟡 unknown | ✅ |
| Public per card verify link | ❌ (PDF) | ❌ 🟡 | 🟡 unknown | ✅ |
| ALTERED check on forwarded copy | ❌ | ❌ | ❌ 🟡 | ✅ |
| Hindi / Hinglish | Hindi as 1 of 16 ✅ | 🟡 | 🟡 | ✅ |

Sources: InTruth + live-fact-checker rows from our repo reads ✅; Veritas ✅ [Devpost](https://devpost.com/software/veritas-grounded-fact-checking-with-gemini), VeriFact ✅ [Devpost](https://devpost.com/software/verifact-ai) (from the verdict md). Cells marked 🟡 = not seen in what we read, which is not proof of absence.

## 6. README credit block (paste as is)

> Inspired by prior work on live fact checking (InTruth, live-fact-checker, ClaimBuster, Full Fact). No code from these projects is included. Third party libraries and their licences are listed in THIRD_PARTY_NOTICES.md.
