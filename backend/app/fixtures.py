"""Offline demo data for PC_MODEL_MODE=stub (tests, CI, local dev before GCP exists).

Facts here are well known, stable ones so the offline demo never shows a wrong card.
Real runs use Gemini with Google Search grounding instead (model.VertexModel).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import Verdict


@dataclass(frozen=True)
class FixtureClaim:
    text: str
    lang: str
    why: str


@dataclass(frozen=True)
class FixtureAssessment:
    verdict: Verdict
    explanation: str
    url: str
    title: str
    passage: str


_FACTS: list[tuple[FixtureClaim, FixtureAssessment]] = [
    (
        FixtureClaim(
            "India has 22 languages in the Eighth Schedule of the Constitution",
            "en",
            "language policy comes up often",
        ),
        FixtureAssessment(
            Verdict.TRUE,
            "The Eighth Schedule of the Constitution of India lists 22 languages.",
            "https://en.wikipedia.org/wiki/Eighth_Schedule_to_the_Constitution_of_India",
            "Eighth Schedule to the Constitution of India",
            "The Eighth Schedule to the Constitution of India lists the official languages of the Republic of India. At present there are 22 languages in the schedule.",
        ),
    ),
    (
        FixtureClaim(
            "Samvidhan 26 January 1950 ko lagu hua tha", "hi-Latn", "Republic Day references"
        ),
        FixtureAssessment(
            Verdict.TRUE,
            "The Constitution of India came into effect on 26 January 1950, now Republic Day.",
            "https://en.wikipedia.org/wiki/Constitution_of_India",
            "Constitution of India",
            "The constitution came into effect on 26 January 1950, which is celebrated as Republic Day in India.",
        ),
    ),
    (
        FixtureClaim(
            "Chandrayaan-3 landed near the Moon's south pole in August 2023",
            "en",
            "space achievements",
        ),
        FixtureAssessment(
            Verdict.TRUE,
            "Chandrayaan-3's Vikram lander touched down near the lunar south pole on 23 August 2023.",
            "https://en.wikipedia.org/wiki/Chandrayaan-3",
            "Chandrayaan-3",
            "The lander touched down near the lunar south pole on 23 August 2023, making India the first country to land near the south pole of the Moon.",
        ),
    ),
    (
        FixtureClaim("Mount Everest is located inside India", "en", "common geography myth"),
        FixtureAssessment(
            Verdict.FALSE,
            "Mount Everest lies on the border of Nepal and the Tibet Autonomous Region of China, not in India.",
            "https://en.wikipedia.org/wiki/Mount_Everest",
            "Mount Everest",
            "The China and Nepal border runs across its summit point. Mount Everest is located in the Mahalangur Himal sub range of the Himalayas.",
        ),
    ),
    (
        FixtureClaim(
            "India ki aabadi duniya mein sabse zyada hai", "hi-Latn", "population rank claims recur"
        ),
        FixtureAssessment(
            Verdict.TRUE,
            "UN estimates show India overtook China as the most populous country in 2023.",
            "https://en.wikipedia.org/wiki/Demographics_of_India",
            "Demographics of India",
            "India is the most populous country in the world, having overtaken China in 2023 according to United Nations estimates.",
        ),
    ),
    (
        FixtureClaim("The Taj Mahal was built in a single year", "en", "heritage myths"),
        FixtureAssessment(
            Verdict.FALSE,
            "Construction of the Taj Mahal took about two decades, roughly 1632 to 1653.",
            "https://en.wikipedia.org/wiki/Taj_Mahal",
            "Taj Mahal",
            "Construction of the mausoleum was essentially completed in 1643, but work continued on other phases of the project for another 10 years. The complex is believed to have been completed in its entirety in 1653.",
        ),
    ),
]

_UNKNOWN = FixtureAssessment(
    Verdict.UNVERIFIABLE,
    "Offline demo mode has no evidence for this claim. Connect the live model to check it.",
    "https://en.wikipedia.org/wiki/Fact-checking",
    "Fact-checking",
    "Fact-checking is the process of verifying the factual accuracy of questioned reporting and statements.",
)


def claims_for_topic(topic: str) -> list[FixtureClaim]:
    return [c for c, _ in _FACTS]


def assessment_for(claim: str) -> FixtureAssessment:
    key = claim.strip().lower()
    for c, a in _FACTS:
        if c.text.lower() == key:
            return a
    return _UNKNOWN


def page_for(url: str) -> bytes | None:
    """Fake page body for the offline fetcher: the passage wrapped in minimal HTML."""
    for _, a in [*_FACTS, (None, _UNKNOWN)]:
        if a.url == url:
            return f"<html><head><title>{a.title}</title></head><body><p>{a.passage}</p></body></html>".encode()
    return None
