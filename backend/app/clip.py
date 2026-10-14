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
from typing import Any, Protocol

# Inline request data stays well under the Gemini request size limit; ~15 min of mp3 at
# 128 kbps is ~14 MB. Larger files: trim or re-encode before upload.
MAX_CLIP_BYTES = 20 * 1024 * 1024
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
    def __init__(self, project: str, location: str, model: str = "gemini-3.5-transcribe") -> None:
        from google import genai

        self.client = genai.Client(vertexai=True, project=project, location=location)
        self.model = model

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
