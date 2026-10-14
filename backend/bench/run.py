"""H2 benchmark runner: the numbers the deck quotes come from here, nowhere else.

    python -m bench.run --mode vertex --out bench/results/2026-10-16.json   # real services
    python -m bench.run --mode stub                                          # wiring check

Measures, per language (en / hi / hi-Latn):
* accuracy: card verdict == gold label (FALSE vs TRUE), on H1 (bench/h1_gold.jsonl);
* proof rate: share of claims that got a card with >= 1 fetched, hashed source;
* UNVERIFIABLE rate: the faithfulness gate refusing a hard verdict;
* cold check latency p50 / p95 (claim in -> card out: model + fetch + match + hash);
* live instant match: hit rate + latency for spoken paraphrases of proved claims, and
  false match rate on chit chat (bench/h1_chitchat.txt);
* tamper: recompressed originals must be VERIFIED, painted edits must be ALTERED.

Stub mode only proves the harness runs: fixtures don't know the gold claims, so its
accuracy is meaningless. Quote vertex runs only, with the JSON file next to the slide.
"""

from __future__ import annotations

import argparse
import io
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app import alter
from app.card_image import render
from app.live import LiveDeps, LiveEngine
from app.pipeline import Deps, build_card
from app.schemas import CardDoc, ClaimDoc, ClaimSource, ClaimStatus, SessionDoc, Verdict
from app.store import InMemoryStore, new_card_id

HERE = Path(__file__).parent
GOLD = HERE / "h1_gold.jsonl"
CHITCHAT = HERE / "h1_chitchat.txt"
BASE = "https://proofcard.example"


@dataclass(frozen=True)
class Gold:
    id: str
    lang: str
    claim: str
    expected: Verdict
    source: str
    spoken: str = ""


@dataclass
class Row:
    id: str
    lang: str
    expected: str
    verdict: str | None  # None = no card (no source survived)
    sources: int
    latency_ms: int
    card_id: str | None = None


@dataclass
class Report:
    mode: str
    n: int
    by_lang: dict[str, dict[str, float]] = field(default_factory=dict)
    overall: dict[str, float] = field(default_factory=dict)
    live: dict[str, float] = field(default_factory=dict)
    tamper: dict[str, float] = field(default_factory=dict)
    rows: list[Row] = field(default_factory=list)


def load_gold(path: Path = GOLD) -> list[Gold]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out.append(Gold(**{**d, "expected": Verdict(d["expected"])}))
    return out


def _pct(xs: list[int], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return float(s[min(len(s) - 1, round(q * (len(s) - 1)))])


def summarize(rows: Iterable[Row]) -> dict[str, float]:
    rs = list(rows)
    n = len(rs) or 1
    lat = [r.latency_ms for r in rs]
    return {
        "n": len(rs),
        "accuracy": round(sum(r.verdict == r.expected for r in rs) / n, 3),
        "proof_rate": round(sum(r.sources > 0 for r in rs) / n, 3),
        "unverifiable_rate": round(sum(r.verdict == "UNVERIFIABLE" for r in rs) / n, 3),
        "latency_p50_ms": _pct(lat, 0.5),
        "latency_p95_ms": _pct(lat, 0.95),
    }


def run_accuracy(
    gold: list[Gold], deps: Deps, clock: Callable[[], float] = time.perf_counter
) -> list[Row]:
    rows = []
    for g in gold:
        t0 = clock()
        card: CardDoc | None
        try:
            card = build_card(g.claim, deps.model.assess(g.claim), deps)
        except Exception:  # a crash is a miss, not a stopped benchmark
            card = None
        ms = int((clock() - t0) * 1000)
        cid = None
        if card is not None:
            cid = new_card_id()
            deps.store.put_card(cid, card)
        rows.append(
            Row(
                g.id,
                g.lang,
                g.expected.value,
                card.verdict.value if card else None,
                len(card.sources) if card else 0,
                ms,
                cid,
            )
        )
    return rows


def run_live(
    gold: list[Gold], rows: list[Row], live: LiveDeps, chitchat: list[str]
) -> dict[str, float]:
    """Prebunk every proved gold claim into one session, then replay spoken lines."""
    store = live.deps.store
    sid = store.create_session(SessionDoc(owner_uid="bench", topic="H1"))
    by_id = {r.id: r for r in rows}
    claim_of: dict[str, str] = {}
    for g in gold:
        r = by_id[g.id]
        if r.card_id is None:
            continue
        cid = store.add_claim(
            sid, ClaimDoc(text=g.claim, lang=g.lang, source=ClaimSource.PREDICTED)
        )
        store.update_claim(sid, cid, status=ClaimStatus.PROVED, card_id=r.card_id)
        claim_of[g.id] = cid

    async def noop(_ev: dict[str, object]) -> None:
        return None

    engine = LiveEngine(sid, live, noop)
    engine.match("warm up")  # first call builds the index; not a per sentence cost
    spoken = [g for g in gold if g.spoken and g.id in claim_of]
    hits, lat = 0, []
    for g in spoken:
        t0 = time.perf_counter()
        got, _ = engine.match(g.spoken)
        lat.append(int((time.perf_counter() - t0) * 1000))
        hits += got == claim_of[g.id]
    false = sum(engine.match(line)[0] is not None for line in chitchat)
    return {
        "spoken_n": len(spoken),
        "instant_match_rate": round(hits / len(spoken), 3) if spoken else 0.0,
        "match_p50_ms": _pct(lat, 0.5),
        "match_p95_ms": _pct(lat, 0.95),
        "chitchat_n": len(chitchat),
        "chitchat_false_match_rate": round(false / len(chitchat), 3) if chitchat else 0.0,
    }


def _jpeg(img: Image.Image, q: int, scale: float) -> bytes:
    small = img.resize((int(img.width * scale), int(img.height * scale)))
    buf = io.BytesIO()
    small.convert("RGB").save(buf, "JPEG", quality=q)
    return buf.getvalue()


# Typical forwarding damage (WhatsApp / Telegram recompress + resize) and typical edits.
RECOMPRESS = [(90, 1.0), (60, 0.75), (40, 0.5)]
EDIT_BOXES = {
    "verdict": (72, 160, 560, 290),
    "claim": (300, 345, 620, 420),
    "sources": (90, 1100, 500, 1135),
}


def run_tamper(store: InMemoryStore, card_ids: list[str], bot: str = "") -> dict[str, float]:
    clean = clean_ok = edited = caught = 0
    for cid in card_ids:
        card = store.get_card(cid)
        if card is None:
            continue
        img = render(card, cid, BASE, bot)
        for q, scale in RECOMPRESS:
            clean += 1
            r = alter.check_image(_jpeg(img, q, scale), store.get_card, BASE, bot)
            clean_ok += r.result == "VERIFIED"
        for box in EDIT_BOXES.values():
            e = img.copy()
            ImageDraw.Draw(e).rectangle(box, fill=(185, 28, 28))
            edited += 1
            caught += (
                alter.check_image(_jpeg(e, 50, 0.66), store.get_card, BASE, bot).result == "ALTERED"
            )
    return {
        "clean_n": clean,
        "clean_verified_rate": round(clean_ok / clean, 3) if clean else 0.0,
        "edited_n": edited,
        "edit_caught_rate": round(caught / edited, 3) if edited else 0.0,
    }


def run(mode: str, deps: Deps, live: LiveDeps, gold: list[Gold], chitchat: list[str]) -> Report:
    rows = run_accuracy(gold, deps)
    rep = Report(mode=mode, n=len(rows), rows=rows)
    rep.overall = summarize(rows)
    for lang in sorted({r.lang for r in rows}):
        rep.by_lang[lang] = summarize(r for r in rows if r.lang == lang)
    rep.live = run_live(gold, rows, live, chitchat)
    store = deps.store
    if not isinstance(store, InMemoryStore):
        raise TypeError("benchmark runs on an in memory store only")
    rep.tamper = run_tamper(store, [r.card_id for r in rows if r.card_id])
    return rep


def to_markdown(rep: Report) -> str:
    lines = [
        f"# H2 benchmark · mode {rep.mode} · {rep.n} claims",
        "",
        "| lang | n | accuracy | proof rate | unverifiable | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for lang, s in [*rep.by_lang.items(), ("all", rep.overall)]:
        lines.append(
            f"| {lang} | {s['n']:.0f} | {s['accuracy']:.0%} | {s['proof_rate']:.0%} | "
            f"{s['unverifiable_rate']:.0%} | {s['latency_p50_ms']:.0f} | "
            f"{s['latency_p95_ms']:.0f} |"
        )
    lines += ["", "Live: " + json.dumps(rep.live), "Tamper: " + json.dumps(rep.tamper)]
    return "\n".join(lines) + "\n"


def _wire(mode: str) -> tuple[Deps, LiveDeps]:  # pragma: no cover - needs settings / GCP
    from app.config import Settings
    from app.main import default_deps, default_live

    settings = Settings(model_mode=mode)
    store = InMemoryStore()  # results never touch Firestore
    deps = default_deps(settings, store)
    live, _ = default_live(settings, deps)
    return deps, live


def main(argv: list[str] | None = None) -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mode", choices=["stub", "vertex"], default="stub")
    ap.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    a = ap.parse_args(argv)
    deps, live = _wire(a.mode)
    chit = [x for x in CHITCHAT.read_text(encoding="utf-8").splitlines() if x.strip()]
    rep = run(a.mode, deps, live, load_gold(), chit)
    print(to_markdown(rep))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = asdict(rep)
        a.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    main()
