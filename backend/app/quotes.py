"""Quote attribution: "Modi said '...'" is first a claim that he SAID it.

Fake quotes put in a politician's mouth are the commonest AI fake-news format (a made up
line on a photo of the speaker, a cloned voice). Checking only the content of such a line
("is X true?") misses the lie that matters: he never said it. p41 (16 Oct 2026).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_Q = r"[\"“”‘’'«»]"  # noqa: RUF001
_WHO = r"(?P<who>[^\n\"“”:]{2,60}?)"
_VERB = (
    r"(?:said|says|has said|had said|stated|told [^\n:\"“”]{1,30}?|claimed|claims|declared|"
    r"announced|tweeted|posted)"
)
_NAME = r"(?P<who>(?:(?:PM|Dr\.?|Mr\.?|Shri)\s+)?[A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){0,3}(?:\s+ji)?)"
_PLAIN_VERB = r"said|says|has said|claimed|claims|declared|announced|tweeted|posted"
PATTERNS = (
    # Modi said: "..."   /   Rahul Gandhi claimed that "..."
    re.compile(rf"^{_WHO}\s+{_VERB}\s*(?:that\s*)?[:,\-]?\s*{_Q}(?P<quote>.+?){_Q}\s*\.?$", re.I),
    # Modi said that India ... (no quote marks, needs 'that')
    re.compile(rf"^{_WHO}\s+{_VERB}\s+that\s+(?P<quote>.+?)\.?$", re.I),
    # Narendra Modi said India became ... (no quote marks, no 'that': a capitalised name,
    # case sensitive so "the report said ..." never reads as a speaker). Prod bot 17 Oct:
    # this form skipped the attribution check, so only the number was checked.
    re.compile(rf"^{_NAME}\s+(?:{_PLAIN_VERB})\s+(?P<quote>[^\"“”].+?)\.?$"),
    # According to Modi, India ...  /  Modi ji ke mutabik ...
    re.compile(rf"^according\s+to\s+{_WHO}\s*,\s*(?P<quote>.+?)\.?$", re.I),
    re.compile(
        rf"^{_WHO}\s+(?:ke\s+mutabik|ke\s+anusaar|के\s+मुताबिक|के\s+अनुसार)\s*,?\s*(?P<quote>.+?)[.।]?$",
        re.I,
    ),
    # Modi ne kaha ki "..."  /  मोदी ने कहा कि ...
    re.compile(
        rf"^{_WHO}\s+(?:ne\s+kaha|ne\s+bola|ने\s+कहा|ने\s+बोला)\s*(?:ki|kee|कि|:)?\s*{_Q}?"
        rf"(?P<quote>.+?){_Q}?\s*[.।]?$",
        re.I,
    ),
    # Modi: "..."
    re.compile(rf"^{_WHO}\s*:\s*{_Q}(?P<quote>.+?){_Q}\s*\.?$", re.I),
    # "..." - Modi
    re.compile(rf"^{_Q}(?P<quote>.+?){_Q}\s*[-–—]+\s*{_WHO}\s*\.?$", re.I),  # noqa: RUF001
)
MIN_QUOTE_WORDS = 4
_NOT_A_SPEAKER = re.compile(
    r"\b(report|reports|study|survey|data|government data|government|ministry|officials|"
    r"experts|analysts|police|court|it|this|they|he|she|people|sources)\b",
    re.I,
)


@dataclass(frozen=True)
class Attribution:
    speaker: str
    quote: str


def attribution(text: str) -> Attribution | None:
    """The speaker and the words put in their mouth, None for any other line."""
    t = " ".join(text.split())
    for p in PATTERNS:
        m = p.match(t)
        if m is None:
            continue
        who = m.group("who").strip(" ,-")
        quote = m.group("quote").strip(" \"“”‘’'")  # noqa: RUF001
        last = who.split()[-1] if who else ""
        if len(quote.split()) < MIN_QUOTE_WORDS or not who or _NOT_A_SPEAKER.fullmatch(last):
            continue
        if len(who.split()) > 6:  # a clause, not a name ("the data released last week...")
            continue
        return Attribution(who, quote)
    return None


def surname(speaker: str) -> str:
    """The word a page about this speaker always contains ("Narendra Modi" -> "modi")."""
    words = re.findall(r"[\w\u0900-\u097F]+", speaker.lower())
    words = [
        w
        for w in words
        if w not in {"pm", "prime", "minister", "president", "shri", "dr", "mr", "ji"}
    ]
    return words[-1] if words else ""
