# Benchmark (H1 gold set + H2 runner)

Every number on the deck comes from a committed run of this runner, file next to the slide. No hand typed numbers.

## H1 gold set · `h1_gold.jsonl`
50 claims on stable, public facts: 25 English, 13 Hindi (Devanagari), 12 Hinglish (Latin), 29 TRUE / 21 FALSE, each with the source page the label rests on. 16 rows carry a `spoken` paraphrase (what a speaker would actually say) for the live instant match. `h1_chitchat.txt`: 10 non claims that must never match.

🟡 Draft labels by Agent, checked against the linked pages; Team lead reviews before the first quoted run. Add rows, never edit a label without a source.

## H2 runner · `run.py`
```bash
cd backend
python -m bench.run --mode stub                                       # wiring check only
PC_GCP_PROJECT=<id> python -m bench.run --mode vertex --out bench/results/<date>.json
```
Vertex mode uses the same wiring as prod (`default_deps`, `default_live`: model, fetcher, embeddings) but an in memory store, so nothing lands in Firestore. One run is about 50 grounded calls + ~130 page fetches.

| Metric | Meaning |
|---|---|
| accuracy | card verdict == gold label, per language and overall |
| proof rate | claims that got a card with ≥ 1 fetched, hashed source |
| unverifiable | the faithfulness gate refused a hard verdict |
| latency p50 / p95 | cold check, claim in to card out (model + fetch + match + hash) |
| instant match rate, match ms | spoken paraphrase of a proved claim hits its prebunked card |
| chit chat false match | non claims that wrongly hit a card (must be 0) |
| clean verified, edit caught | ALTERED check on 3 recompress levels and 3 painted edits per card |

Stub mode only proves the harness: fixtures don't know the gold claims, so accuracy is 0% there by design. The tamper numbers are real even in stub mode (rendering and the ALTERED check are the production code); first stub run, 14 Oct: 150/150 recompressed cards VERIFIED, 150/150 edits caught.
