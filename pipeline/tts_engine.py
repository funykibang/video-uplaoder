"""
pipeline.tts_engine
~~~~~~~~~~~~~~~~~~~
Generates a WAV voiceover file from a text script.

Public API
----------
generate_voiceover(script: str, output_path: str, engine="coqui") -> str

Private synthesizers (mock-patchable in tests)
----------------------------------------------
_synthesize_coqui(script, output_path) -> str
_synthesize_piper(script, output_path) -> str
"""

import json
import logging
import os
import subprocess
from typing import Optional

import requests

import config


def _safe_output_path(output_path: str) -> str:
    abs_out = os.path.abspath(config.OUTPUT_DIR)
    abs_path = os.path.abspath(output_path)
    if not abs_path.startswith(abs_out + os.sep) and abs_path != abs_out:
        raise ValueError(f"output_path escapes OUTPUT_DIR: {output_path!r}")
    return output_path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class TTSError(RuntimeError):
    """Raised when TTS synthesis fails."""


# ---------------------------------------------------------------------------
# Coqui TTS backend
# ---------------------------------------------------------------------------

try:
    from TTS.api import TTS  # type: ignore
except ImportError:  # pragma: no cover
    TTS = None  # type: ignore


def _synthesize_coqui(script: str, output_path: str) -> str:
    """
    Synthesise *script* to *output_path* using Coqui XTTS-v2.

    Returns *output_path* on success.  Raises TTSError on any failure.
    """
    try:
        if TTS is None:
            raise TTSError("Coqui TTS is not installed. Run: pip install TTS")
        output_path = _safe_output_path(output_path)
        tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                  progress_bar=False,
                  gpu=True)
        tts.tts_to_file(
            text=script,
            file_path=output_path,
            language="en",
        )
        return output_path
    except Exception as exc:
        raise TTSError(f"Coqui TTS failed: {exc}") from exc


# ---------------------------------------------------------------------------
# ElevenLabs TTS backend
# ---------------------------------------------------------------------------

_VOICE_MAP = {
    "SCIENTIST": lambda: config.ELEVENLABS_SCIENTIST_VOICE,
    "VILLAGER":  lambda: config.ELEVENLABS_VILLAGER_VOICE,
}


def _elevenlabs_pcm(text: str, voice_id: str) -> bytes:
    """Fetch raw PCM 22050 Hz mono from ElevenLabs for *text*."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": config.ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    payload = {"text": text, "model_id": config.ELEVENLABS_MODEL}
    try:
        resp = requests.post(
            url,
            params={"output_format": "pcm_22050"},
            json=payload,
            headers=headers,
            timeout=60,
        )
    except requests.exceptions.RequestException as exc:
        raise TTSError(f"ElevenLabs network error: {exc}") from exc
    if resp.status_code != 200:
        raise TTSError(f"ElevenLabs API error {resp.status_code}: {resp.text[:200]}")
    return resp.content


def _synthesize_elevenlabs(script: str, output_path: str) -> str:
    """
    Parse SCIENTIST/VILLAGER dialogue, synthesise each line with its voice,
    concatenate PCM chunks, write a single WAV, and save a speaker timings sidecar.
    """
    output_path = _safe_output_path(output_path)

    lines = [l.strip() for l in script.splitlines() if l.strip()]
    pcm_chunks = []
    timings = []
    current_time = 0.0

    for line in lines:
        for speaker, voice_fn in _VOICE_MAP.items():
            prefix = f"{speaker}:"
            if line.startswith(prefix):
                text = line[len(prefix):].strip()
                if text:
                    pcm = _elevenlabs_pcm(text, voice_fn())
                    duration = len(pcm) / (22050 * 2)  # 16-bit mono = 2 bytes/sample
                    timings.append({
                        "speaker": speaker,
                        "start": round(current_time, 3),
                        "end": round(current_time + duration, 3),
                    })
                    current_time += duration
                    pcm_chunks.append(pcm)
                break

    if not pcm_chunks:
        raise TTSError("No speakable dialogue lines found in script.")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Write raw PCM then convert to WAV via ffmpeg so faster-whisper reads it correctly
    pcm_path = output_path.replace(".wav", ".pcm")
    with open(pcm_path, "wb") as f:
        for chunk in pcm_chunks:
            f.write(chunk)
    try:
        proc = subprocess.run(
            [config.FFMPEG_PATH, "-y", "-f", "s16le", "-ar", "22050", "-ac", "1",
             "-i", pcm_path, output_path],
            capture_output=True,
        )
    finally:
        if os.path.exists(pcm_path):
            os.unlink(pcm_path)
    if proc.returncode != 0:
        raise TTSError(f"WAV conversion failed: {proc.stderr.decode(errors='replace')[:300]}")

    timings_path = output_path.replace(".wav", "_timings.json")
    with open(timings_path, "w") as f:
        json.dump(timings, f)

    return output_path


# ---------------------------------------------------------------------------
# Piper TTS backend (lightweight subprocess wrapper)
# ---------------------------------------------------------------------------

def _synthesize_piper(script: str, output_path: str) -> str:
    """
    Synthesise *script* to *output_path* using piper-tts CLI.

    Returns *output_path* on success.  Raises TTSError on non-zero exit code.
    """
    output_path = _safe_output_path(output_path)
    cmd = [
        "piper",
        "-m", config.PIPER_MODEL,
        "--output_file", output_path,
    ]
    proc = subprocess.run(
        cmd,
        input=script.encode("utf-8"),
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise TTSError(
            f"piper-tts exited with code {proc.returncode}: {proc.stderr.decode()}"
        )
    return output_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_voiceover(
    script: Optional[str],
    output_path: str,
    engine: Optional[str] = None,
) -> str:
    """
    Generate a WAV voiceover from *script* and write it to *output_path*.

    Parameters
    ----------
    script : str
        The narration text to synthesise.
    output_path : str
        Destination file path (must end in .wav).
    engine : str, optional
        "coqui" (default) or "piper".

    Returns
    -------
    str
        The resolved *output_path*.

    Raises
    ------
    ValueError
        If *script* is empty/None, *output_path* is empty, or *engine* is unknown.
    TTSError
        If the underlying TTS call fails.
    """
    # --- input validation ---
    if script is None:
        raise ValueError("script must not be None.")
    if not isinstance(script, str):
        raise TypeError("script must be a str.")
    if not script.strip():
        raise ValueError("script must not be empty.")
    if not output_path:
        raise ValueError("output_path must not be empty.")

    if engine is None:
        engine = config.TTS_ENGINE

    _engines = {"coqui": _synthesize_coqui, "piper": _synthesize_piper, "elevenlabs": _synthesize_elevenlabs}
    if engine not in _engines:
        raise ValueError(
            f"Unknown TTS engine {engine!r}. Choose from: {list(_engines)}"
        )

    synthesize = _engines[engine]
    try:
        result = synthesize(script, output_path)
    except TTSError:
        raise
    except Exception as exc:
        raise TTSError(f"TTS engine '{engine}' raised an unexpected error: {exc}") from exc

    return result
