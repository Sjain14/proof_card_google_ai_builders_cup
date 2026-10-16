"""Clip upload fallback (plan B2, audit #12).

When live tab audio can't be captured (no stream, browser blocks tab audio, Live API
down), the user uploads a recorded audio clip instead. One synchronous call to
gemini-3.5-transcribe turns it into text; every sentence then goes through the SAME
LiveEngine.on_sentence as live speech: instant prebunked match or the cold path.

Docs: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-transcribe
(synchronous transcription via generate_content + AudioTranscriptionConfig, file model
up to 15 min of audio, custom vocabulary up to 1,000 terms).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

# Inline request data stays well under the Gemini request size limit; ~15 min of mp3 at
# 128 kbps is ~14 MB. Larger files: trim or re-encode before upload.
MAX_CLIP_BYTES = 20 * 1024 * 1024
CLIP_BATCH = 10  # lines per saved step of a clip job: a resumed job redoes at most these.
# Each step waits for its slowest check (drain), so 5 made a 9-line clip 2 serial waits
# (prod e2e 16 Oct: 635 s for a 2 min clip); 10 (< the 12 cold workers) runs a short
# clip in one parallel step.
# A job that saved nothing for this long lost its instance (one batch of 10 parallel cold checks
# plus a 9 min clip's transcription stay under it) and is re-queued on the next poll.
CLIP_STALE = timedelta(minutes=15)

if TYPE_CHECKING:
    from app.schemas import ClipJob


def clip_stalled(job: ClipJob, now: datetime | None = None) -> bool:
    return job.state in ("queued", "running") and (now or datetime.now(UTC)) - job.beat > CLIP_STALE


MAX_SENTENCES = 300

# Audio only: the transcribe model takes audio input, not video.
CLIP_MIME = {
    "audio/mpeg": "audio/mpeg",
    "audio/mp3": "audio/mpeg",
    "audio/wav": "audio/wav",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/mp4": "audio/mp4",
    "audio/m4a": "audio/mp4",
    "audio/x-m4a": "audio/mp4",
    "audio/aac": "audio/aac",
    "audio/ogg": "audio/ogg",
    "audio/webm": "audio/webm",
    "audio/flac": "audio/flac",
    "audio/x-flac": "audio/flac",
}

_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n+")


class ClipTranscriber(Protocol):
    def transcribe(self, data: bytes, mime: str, vocabulary: Sequence[str] = ()) -> str: ...


TimedLine = tuple[float, str]  # (second in the clip, sentence)

_MMSS = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)\s*$")


def parse_clock(v: object) -> float | None:
    """ "1:05" / "01:02:03" / "65.5" / 65 -> seconds, else None."""
    if isinstance(v, int | float) and not isinstance(v, bool):
        return float(v) if v >= 0 else None
    if not isinstance(v, str):
        return None
    if m := _MMSS.match(v):
        h, mm, ss = m.groups()
        return int(h or 0) * 3600 + int(mm) * 60 + float(ss)
    try:
        f = float(v)
    except ValueError:
        return None
    return f if f >= 0 else None


_END = re.compile("[.!?\u0964]['\"\u201d\u2019)]*$")
MAX_JOINED_WORDS = 60


def join_fragments(lines: list[TimedLine]) -> list[TimedLine]:
    """The model often returns phrases, not sentences ("Because whether it was in 2008",
    "or before that", "we've never seen"). A claim split across items is never checked
    and never matches the bank (replay 7dhIVHRKhvo: 35 items, 0 bank matches). Join items
    until one ends a sentence; the joined line keeps the first item's start time. Cap at
    MAX_JOINED_WORDS so an unpunctuated transcript can't become one line."""
    out: list[TimedLine] = []
    start: float | None = None
    buf: list[str] = []
    for t, text in lines:
        if start is None:
            start = t
        buf.append(text)
        if _END.search(text) or len(" ".join(buf).split()) >= MAX_JOINED_WORDS:
            out.append((start, " ".join(buf)))
            start, buf = None, []
    if buf and start is not None:
        out.append((start, " ".join(buf)))
    return out


def timed_from_json(items: object) -> list[TimedLine]:
    """Model output [{"start": "MM:SS", "text": ...}] -> sorted, whole timed sentences."""
    raw: list[TimedLine] = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        t, text = parse_clock(it.get("start")), str(it.get("text") or "").strip()
        if t is not None and text:
            raw.append((t, text))
    joined = join_fragments(sorted(raw, key=lambda p: p[0]))
    return [(t, x) for t, x in joined if len(x.split()) >= 3][:MAX_SENTENCES]


TIMED_PROMPT = """Transcribe this audio verbatim, one item per sentence, in the language
spoken (English, Hindi or Hinglish; Hinglish in Latin script). For each sentence give the
time it starts as MM:SS. One item = one complete sentence ending in . ? ! or ।; never
split a sentence across items. Do not summarise, translate or skip anything.
Names and terms that may occur: {vocab}
"""


def clip_mime(content_type: str | None) -> str | None:
    """Canonical mime for an allowed upload, None otherwise."""
    return CLIP_MIME.get((content_type or "").split(";")[0].strip().lower())


def sentences(transcript: str) -> list[str]:
    """Transcript -> sentences for on_sentence. Very short fragments are dropped here;
    the claim spotter decides what is a claim."""
    out = [s.strip() for s in _SPLIT.split(transcript or "")]
    return [s for s in out if len(s.split()) >= 3][:MAX_SENTENCES]


def text_from_response(resp: Any) -> str:
    """Join the transcript parts (text, or audio_transcription.text per the docs)."""
    try:
        parts = resp.candidates[0].content.parts or []
    except (AttributeError, IndexError, TypeError):
        parts = getattr(resp, "parts", None) or []
    chunks: list[str] = []
    for p in parts:
        tx = getattr(p, "audio_transcription", None)
        text = getattr(p, "text", None) or (getattr(tx, "text", None) if tx else None) or ""
        if isinstance(text, str) and text.strip():
            chunks.append(text.strip())
    return "\n".join(chunks)


class GeminiClipTranscriber:  # pragma: no cover - needs a GCP project
    def __init__(
        self,
        project: str,
        location: str,
        model: str = "gemini-3.5-transcribe",
        timed_model: str = "gemini-3.5-flash",
        timed_location: str = "global",
    ) -> None:

        from app.model import vertex_client

        self.client = vertex_client(project, location, 300.0)  # a 15 min clip, one call
        self.model = model
        # retries 429/503 under load (prod e2e 16 Oct: two clips failed in 11 s)
        self.timed_client = vertex_client(project, timed_location, 300.0, attempts=4)
        self.timed_model = timed_model

    def transcribe(self, data: bytes, mime: str, vocabulary: Sequence[str] = ()) -> str:
        from google.genai import types

        resp = self.client.models.generate_content(
            model=self.model,
            contents=types.Part.from_bytes(data=data, mime_type=mime),
            config=types.GenerateContentConfig(
                audio_transcription_config=types.AudioTranscriptionConfig(
                    custom_vocabulary=list(vocabulary) or None,
                ),
            ),
        )
        return text_from_response(resp)

    def transcribe_timed(
        self, data: bytes, mime: str, vocabulary: Sequence[str] = ()
    ) -> list[TimedLine]:
        """Replay clips: sentences with start times, so cards can follow the video.
        Gemini understands audio timestamps in MM:SS:
        https://ai.google.dev/gemini-api/docs/audio#refer-to-timestamps"""
        import json

        from google.genai import types

        contents: list[Any] = [
            types.Part.from_bytes(data=data, mime_type=mime),
            TIMED_PROMPT.format(vocab=", ".join(list(vocabulary)[:200]) or "none"),
        ]
        resp = self.timed_client.models.generate_content(
            model=self.timed_model,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema={
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {"start": {"type": "STRING"}, "text": {"type": "STRING"}},
                        "required": ["start", "text"],
                    },
                },
            ),
        )
        try:
            return timed_from_json(json.loads(resp.text or "[]"))
        except ValueError:
            return []
