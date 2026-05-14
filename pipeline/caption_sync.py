"""
pipeline.caption_sync
~~~~~~~~~~~~~~~~~~~~~
Extracts word-level timestamps from audio and groups them into caption chunks.

Public API
----------
extract_word_timestamps(audio_path: str) -> list[dict]
    Returns [{"word": str, "start": float, "end": float}, ...]

group_into_caption_chunks(words: list, chunk_size=4) -> list[dict]
    Returns [{"text": str, "start_time": float, "end_time": float}, ...]
"""

import logging
import os
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class CaptionSyncError(RuntimeError):
    """Raised when word-timestamp extraction fails."""


# ---------------------------------------------------------------------------
# faster-whisper import (lazy, so tests can mock before import)
# ---------------------------------------------------------------------------

try:
    from faster_whisper import WhisperModel  # type: ignore
except ImportError:  # pragma: no cover
    WhisperModel = None  # type: ignore


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_word_timestamps(audio_path: str) -> List[Dict[str, Any]]:
    """
    Transcribe *audio_path* with faster-whisper and return a flat list of
    per-word timing dicts::

        [{"word": "Hello", "start": 0.0, "end": 0.35}, ...]

    Raises CaptionSyncError on any transcription failure.
    """
    if not os.path.isfile(audio_path):
        raise CaptionSyncError(f"Audio file not found: {audio_path!r}")
    if WhisperModel is None:
        raise CaptionSyncError("faster-whisper is not installed. Run: pip install faster-whisper")
    try:
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(audio_path, word_timestamps=True, vad_filter=False)

        words: List[Dict[str, Any]] = []
        for segment in segments:
            for w in (segment.words or []):
                words.append({
                    "word":  w.word.strip(),
                    "start": float(w.start),
                    "end":   float(w.end),
                })
        return words

    except Exception as exc:
        raise CaptionSyncError(
            f"Word-timestamp extraction failed for '{audio_path}': {exc}"
        ) from exc


def group_into_caption_chunks(
    words: List[Dict[str, Any]],
    chunk_size: int = 4,
) -> List[Dict[str, Any]]:
    """
    Group *words* into fixed-size chunks for on-screen display.

    Each chunk dict contains::

        {"text": str, "start_time": float, "end_time": float}

    Parameters
    ----------
    words : list
        Output from extract_word_timestamps().
    chunk_size : int
        Number of words per caption card (default 4).

    Raises
    ------
    ValueError
        If *chunk_size* is less than 1.
    """
    if chunk_size < 1:
        raise ValueError(f"chunk_size must be >= 1, got {chunk_size}")

    if not words:
        return []

    chunks: List[Dict[str, Any]] = []
    for i in range(0, len(words), chunk_size):
        group = words[i : i + chunk_size]
        text       = " ".join(w["word"] for w in group)
        start_time = group[0]["start"]
        end_time   = group[-1]["end"]
        chunks.append({
            "text":       text,
            "start_time": start_time,
            "end_time":   end_time,
        })
    return chunks
