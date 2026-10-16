"""Model layer: claim prediction (Before) and grounded assessment (During / After).

The pipeline depends on the ModelClient protocol only. Two implementations:

* StubModel: deterministic, offline. Used in tests, CI and local dev before the GCP
  project exists (PC_MODEL_MODE=stub).
* VertexModel: Gemini on Vertex AI. Prediction uses a JSON response schema; assessment
  uses Grounding with Google Search and reads grounding_metadata for the evidence.
  Docs: https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-search

The model never decides the final verdict alone: pipeline.py fetches every source
itself, matches a passage, hashes a snapshot, and gate_verdict() downgrades any hard
verdict the fetched evidence doesn't support.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.schemas import Verdict


@dataclass(frozen=True)
class PredictedClaim:
    text: str
    lang: str = "en"
    why: str = ""


# Every Vertex call is bounded: google-genai has no default timeout, so one stalled call
# hangs its caller forever (rev00012: a brief sat in "prebunking" with 0 claims for 12 min).
# Retries are the SDK's own (429/5xx, exponential backoff with jitter).
# Docs: https://googleapis.github.io/python-genai/genai.html#genai.types.HttpOptions
GENERATE_TIMEOUT_S = 90.0  # grounded assess: search + long answer
FAST_TIMEOUT_S = 10.0  # live path: spotter, judge, embeddings
# Brief bank prediction: one plain JSON list, no search. Prod 16 Oct 2026: speaker
# "Donald Trump" hung predict_claims for 90 s x 3 retries (280 s, session failed) while
# no speaker took ~15 s. Bounded: low thinking, capped output, one 40 s attempt.
PREDICT_TIMEOUT_S = 60.0  # 40 s: 2 of 3 replay briefs failed (16 Oct), fallbacks follow
PREDICT_MAX_TOKENS = 4096


def _fast_thinking() -> Any:
    """Live path classifiers (spotter, judge) answer yes/no or a short list: minimal
    thinking keeps them at ~1 s instead of seconds. The grounded assess keeps the default.
    Docs: https://cloud.google.com/vertex-ai/generative-ai/docs/thinking"""
    from google.genai import types

    return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)


def vertex_client(
    project: str, location: str, timeout_s: float, attempts: int = 3
) -> Any:  # pragma: no cover
    from google import genai
    from google.genai import types

    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=types.HttpOptions(
            timeout=int(timeout_s * 1000),  # milliseconds
            retry_options=types.HttpRetryOptions(attempts=attempts),
        ),
    )


SUGGESTION_MAX = 50_000  # chars; never truncate (that would modify it), drop if larger


@dataclass(frozen=True)
class Evidence:
    url: str
    title: str = ""
    model_snippet: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class Assessment:
    verdict: Verdict
    explanation: str
    evidence: list[Evidence] = field(default_factory=list)
    # The claim restated in English by the same call. Sources are mostly English, so a
    # Hindi / Hinglish claim is matched against pages through this (no extra model call).
    claim_en: str = ""
    # Google Search suggestion chips (grounding_metadata.search_entry_point.rendered_content).
    # Grounding terms: shown exactly as provided wherever the grounded explanation is shown.
    search_suggestion_html: str = ""


class ModelClient(Protocol):
    def predict_claims(self, topic: str, speaker: str, n: int) -> list[PredictedClaim]: ...
    def assess(self, claim: str, hint: str = "") -> Assessment: ...


# ---------- prompts (kept here so they are versioned and reviewable) ----------

PROMPT_VERSION = "2026-10-16.3"

PREDICT_PROMPT = """You are the research desk of an Indian fact-checking newsroom preparing
for a live broadcast. Topic: {topic}
Speaker: {speaker}

List the {n} factual claims most likely to be said on air that a fact checker can verify
against public records (numbers, dates, rankings, official statistics, quotes of policy).
Rules:
- One claim per item, a single sentence, as a speaker would actually say it.
- Prefer claims with numbers. No opinions, predictions or claims about private people.
- Write each claim in the language THIS speaker actually speaks in public: en, hi
  (Devanagari) or hi-Latn (Hinglish in Latin script). A speaker who speaks English (for
  example a US or UK politician) gets every claim in en; only use hi / hi-Latn for a
  speaker who really speaks Hindi or Hinglish. Never translate a claim into another
  language to pad the list: a claim the speaker can't say in that language never matches.
- Include claims this speaker has already made on this topic and that fact checkers have
  rated, phrased the way they said them.
- "why": one short line on why it is likely to come up.
"""

PREDICT_SCHEMA: dict[str, Any] = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "text": {"type": "STRING"},
            "lang": {"type": "STRING", "enum": ["en", "hi", "hi-Latn"]},
            "why": {"type": "STRING"},
        },
        "required": ["text", "lang"],
    },
}

ASSESS_PROMPT = """Fact check this claim using Google Search. Claim: "{claim}"

Answer in EXACTLY this format, nothing else:
VERDICT: <TRUE|FALSE|MISLEADING|UNVERIFIABLE>
CLAIM_EN: <the claim restated as one plain English sentence, same numbers and names>
EXPLANATION: <at most 60 words, plain English, cite the official figure and its date>

Judge whether the claim itself is true, never whether the speaker said it: a report that
the speaker made this claim ("he said...", a quote of the speech) is NOT evidence for it.
TRUE needs a source that states the fact independently (records, official data, reporting
of what actually happened). Only a quote = UNVERIFIABLE.
Use UNVERIFIABLE when reliable sources disagree or are missing. Prefer official and
primary sources (government statistics, regulators, court records) over news.
"""

_VERDICT_RE = re.compile(r"VERDICT:\s*(TRUE|FALSE|MISLEADING|UNVERIFIABLE)", re.IGNORECASE)
_EXPL_RE = re.compile(r"EXPLANATION:\s*(.+)", re.IGNORECASE | re.DOTALL)
_CLAIM_EN_RE = re.compile(r"CLAIM_EN:\s*(.+)", re.IGNORECASE)


def parse_claim_en(text: str) -> str:
    m = _CLAIM_EN_RE.search(text or "")
    return m.group(1).strip()[:500] if m else ""


def parse_assessment_text(text: str) -> tuple[Verdict, str]:
    """Parse the strict two line answer. Anything malformed becomes UNVERIFIABLE."""
    m = _VERDICT_RE.search(text or "")
    verdict = Verdict(m.group(1).upper()) if m else Verdict.UNVERIFIABLE
    e = _EXPL_RE.search(text or "")
    explanation = (e.group(1).strip() if e else "").strip()[:600]
    return verdict, explanation or "The model gave no explanation."


def parse_predictions(raw: str, n: int) -> list[PredictedClaim]:
    try:
        items = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    out: list[PredictedClaim] = []
    seen: set[str] = set()
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text", "")).strip()[:500]
        lang = it.get("lang", "en")
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(
            PredictedClaim(
                text=text,
                lang=lang if lang in {"en", "hi", "hi-Latn"} else "en",
                why=str(it.get("why", "")).strip()[:200],
            )
        )
    return out[:n]


# ---------- stub ----------


class StubModel:
    """Deterministic offline model. Uses fixtures.py so the demo works without GCP."""

    def predict_claims(self, topic: str, speaker: str, n: int) -> list[PredictedClaim]:
        from app.fixtures import claims_for_topic

        return [
            PredictedClaim(text=c.text, lang=c.lang, why=c.why) for c in claims_for_topic(topic)
        ][:n]

    def assess(self, claim: str, hint: str = "") -> Assessment:
        from app.fixtures import assessment_for

        fx = assessment_for(claim)
        return Assessment(
            verdict=fx.verdict,
            explanation=fx.explanation,
            evidence=[
                Evidence(url=fx.url, title=fx.title, model_snippet=fx.passage, confidence=0.9)
            ],
            claim_en=claim,
        )


# ---------- Vertex AI ----------


class VertexModel:  # pragma: no cover - needs a GCP project; covered by the parsing tests
    def __init__(self, project: str, location: str, model: str) -> None:
        self.client = vertex_client(project, location, GENERATE_TIMEOUT_S)
        self.model = model

    def predict_claims(self, topic: str, speaker: str, n: int) -> list[PredictedClaim]:
        from google.genai import types

        resp = self.client.models.generate_content(
            model=self.model,
            contents=PREDICT_PROMPT.format(topic=topic, speaker=speaker or "unknown", n=n),
            config=types.GenerateContentConfig(
                temperature=0.4,
                response_mime_type="application/json",
                response_schema=PREDICT_SCHEMA,
                max_output_tokens=PREDICT_MAX_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
                http_options=types.HttpOptions(
                    timeout=int(PREDICT_TIMEOUT_S * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            ),
        )
        return parse_predictions(resp.text or "", n)

    def assess(self, claim: str, hint: str = "") -> Assessment:
        from google.genai import types

        resp = self.client.models.generate_content(
            model=self.model,
            contents=ASSESS_PROMPT.format(claim=claim) + (f"\n{hint}\n" if hint else ""),
            config=types.GenerateContentConfig(
                temperature=0.0,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        raw = resp.text or ""
        verdict, explanation = parse_assessment_text(raw)
        return Assessment(
            verdict,
            explanation,
            evidence_from_grounding(resp),
            parse_claim_en(raw),
            search_suggestion_from(resp),
        )


def search_suggestion_from(resp: Any) -> str:
    """rendered_content of the Search suggestion, untouched (we must not modify it).
    Docs: https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-search-suggestions"""
    try:
        sep = resp.candidates[0].grounding_metadata.search_entry_point
        html = getattr(sep, "rendered_content", None) or ""
    except (AttributeError, IndexError, TypeError):
        return ""
    return html if isinstance(html, str) and len(html) <= SUGGESTION_MAX else ""


def evidence_from_grounding(resp: Any) -> list[Evidence]:
    """Turn grounding_metadata into Evidence, best supported chunks first."""
    try:
        meta = resp.candidates[0].grounding_metadata
    except (AttributeError, IndexError, TypeError):
        return []
    if meta is None:
        return []
    chunks = list(getattr(meta, "grounding_chunks", None) or [])
    best: dict[int, tuple[float, str]] = {}
    for sup in getattr(meta, "grounding_supports", None) or []:
        seg = getattr(getattr(sup, "segment", None), "text", "") or ""
        scores = list(getattr(sup, "confidence_scores", None) or [])
        for pos, idx in enumerate(getattr(sup, "grounding_chunk_indices", None) or []):
            conf = float(scores[pos]) if pos < len(scores) else 0.0
            if idx not in best or conf > best[idx][0]:
                best[idx] = (conf, seg)
    out: list[Evidence] = []
    for idx, ch in enumerate(chunks):
        web = getattr(ch, "web", None)
        uri = getattr(web, "uri", None)
        if not uri:
            continue
        conf, seg = best.get(idx, (0.0, ""))
        out.append(
            Evidence(
                url=uri, title=getattr(web, "title", "") or "", model_snippet=seg, confidence=conf
            )
        )
    out.sort(key=lambda e: e.confidence, reverse=True)
    return out
