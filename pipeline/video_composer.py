"""
pipeline.video_composer
~~~~~~~~~~~~~~~~~~~~~~~
Composes the final 1080 x 1920 MP4 with burned ASS captions and voiceover.

Public API
----------
compose_video(background_path, audio_path, captions, output_path,
              resolution=(1080, 1920)) -> str

Private helpers (mock-patchable in tests)
-----------------------------------------
_build_ass_subtitles(captions) -> str
_format_ass_timestamp(seconds) -> str
_run_ffmpeg(cmd) -> None
"""

import json
import logging
import math
import os
import random
import struct
import subprocess
import wave
from typing import List, Dict, Any, Tuple

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class VideoComposerError(RuntimeError):
    """Raised when video composition fails."""


# ---------------------------------------------------------------------------
# ASS subtitle helpers
# ---------------------------------------------------------------------------

def _format_ass_timestamp(seconds: float) -> str:
    """
    Convert *seconds* to ASS timestamp format: H:MM:SS.cc
    (centiseconds, not milliseconds).
    """
    total_cs = round(seconds * 100)
    cs   = total_cs % 100
    total_s = total_cs // 100
    s    = total_s % 60
    total_m = total_s // 60
    m    = total_m % 60
    h    = total_m // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{primary},{secondary},{outline},{back},1,0,0,0,100,100,0,0,1,3,0,2,10,10,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _build_ass_subtitles(
    captions: List[Dict[str, Any]],
    resolution: Tuple[int, int] = (1080, 1920),
) -> str:
    """Build a full ASS subtitle file string from *captions*."""
    width, height = resolution
    header = _ASS_HEADER.format(
        width=width,
        height=height,
        font=config.CAPTION_FONT,
        font_size=config.CAPTION_FONT_SIZE,
        primary=config.CAPTION_PRIMARY_COLOUR,
        secondary=config.CAPTION_PRIMARY_COLOUR,
        outline=config.CAPTION_OUTLINE_COLOUR,
        back="&H00000000",
    )

    lines = []
    for cap in captions:
        start = _format_ass_timestamp(cap["start_time"])
        end   = _format_ass_timestamp(cap["end_time"])
        text  = cap["text"].replace("\n", "\\N")
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    return header + "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# FFmpeg runner (isolated so tests can mock it cleanly)
# ---------------------------------------------------------------------------

def _probe_duration(video_path: str) -> float:
    """Return duration in seconds of *video_path* using ffprobe."""
    cmd = [
        config.FFPROBE_PATH, "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.decode(errors='replace')}")
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


_SAMPLE_RATE = 22050
_SLIDE_DUR   = 0.35   # seconds to slide fully into frame
_CHAR_W      = 320
_CHAR_IMAGES = {
    "SCIENTIST": os.path.join("assets", "characters", "scientist.png"),
    "VILLAGER":  os.path.join("assets", "characters", "farmer.png"),
}


def _generate_pop_track(timings: list, total_duration: float) -> str:
    """Write a WAV with a swoosh sound at the start of each speaker segment."""
    total_samples = int((total_duration + 0.5) * _SAMPLE_RATE)
    data = bytearray(total_samples * 2)
    swoosh_len = int(0.28 * _SAMPLE_RATE)
    for seg in timings:
        offset = int(seg["start"] * _SAMPLE_RATE)
        for i in range(swoosh_len):
            p = i / swoosh_len
            t = i / _SAMPLE_RATE
            freq = 2400 * math.exp(-p * math.log(2400 / 280))  # sweep 2400 Hz → 280 Hz
            env  = (p / 0.08) if p < 0.08 else math.exp(-4.5 * (p - 0.08))
            sample = (0.65 * math.sin(2 * math.pi * freq * t)
                      + 0.35 * (random.random() * 2 - 1)) * env
            value = max(-32768, min(32767, int(sample * 5500)))
            idx = (offset + i) * 2
            if idx + 1 < len(data):
                struct.pack_into("<h", data, idx, value)
    path = os.path.join(config.OUTPUT_DIR, "swoosh_track.wav")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(bytes(data))
    return path


def _build_filter_complex(
    timings: list,
    width: int,
    height: int,
    ffmpeg_ass_path: str,
    media_inserts: List[Dict[str, Any]] = None,
) -> str:
    """Build a filter_complex string with slide-in character overlays and captions.

    If *media_inserts* is provided each entry {"path", "start", "end"} is
    overlaid in the upper area of the frame (above the character sprites)
    using an ``enable`` expression so it appears only during its window.
    The corresponding FFmpeg inputs must be appended to the command starting
    at input index 5 (0-4 are bg, audio, sci, vil, pop).
    """
    sci_segs = [(s["start"], s["end"]) for s in timings if s["speaker"] == "SCIENTIST"]
    vil_segs = [(s["start"], s["end"]) for s in timings if s["speaker"] == "VILLAGER"]

    def _enable(segs):
        return "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in segs) or "0"

    def _progress(segs):
        """Per-segment slide progress: 0 at segment start → 1 after SLIDE_DUR seconds."""
        if not segs:
            return "0"
        parts = [
            f"max(0,min(1,(t-{s:.3f})/{_SLIDE_DUR:.2f}))*between(t,{s:.3f},{e:.3f})"
            for s, e in segs
        ]
        return "+".join(parts)

    sci_prog = _progress(sci_segs)
    vil_prog = _progress(vil_segs)

    # SCIENTIST: slides in from the right  (x: W → W-w-40)
    sci_x = f"W-({_CHAR_W}+40)*({sci_prog})"
    # VILLAGER:  slides in from the left   (x: -w → 40)
    vil_x = f"-{_CHAR_W}+({_CHAR_W}+40)*({vil_prog})"

    y_pos = int(height * 0.52)

    inserts = media_inserts or []
    # Height of the insert panel: upper ~42 % of the frame (above characters)
    insert_h = int(height * 0.42)
    show_dur = getattr(config, "MEDIA_INSERT_SHOW_DURATION", 3.5)

    parts: List[str] = [
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2[bg]",
        f"[2:v]scale={_CHAR_W}:-2[sci]",
        f"[3:v]scale={_CHAR_W}:-2[vil]",
    ]

    # Build per-insert filter chain (index 5, 6, …)
    for i, ins in enumerate(inserts):
        idx = 5 + i
        kind = ins.get("kind", "image")
        if kind == "video":
            # Trim to the insert's own display window length, shift PTS to start time
            clip_dur = max(round(ins["end"] - ins["start"], 3), 1.0)
            parts.append(
                f"[{idx}:v]trim=end={clip_dur:.3f},setpts=PTS-STARTPTS+{ins['start']:.3f}/TB,"
                f"scale={width}:{insert_h}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{insert_h}:(ow-iw)/2:(oh-ih)/2[ins{i}]"
            )
        else:
            # Image: already looped via -loop 1 on the input side
            parts.append(
                f"[{idx}:v]scale={width}:{insert_h}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{insert_h}:(ow-iw)/2:(oh-ih)/2[ins{i}]"
            )

    # Chain overlays: background → inserts (top panel) → characters → captions
    current = "bg"
    for i, ins in enumerate(inserts):
        kind = ins.get("kind", "image")
        next_v = f"bm{i}"
        if kind == "video":
            # PTS-shifted video: overlay without enable; eof_action=pass lets bg show through after clip ends
            parts.append(f"[{current}][ins{i}]overlay=0:0:eof_action=pass[{next_v}]")
        else:
            enable = f"between(t,{ins['start']:.3f},{ins['end']:.3f})"
            parts.append(f"[{current}][ins{i}]overlay=0:0:enable='{enable}'[{next_v}]")
        current = next_v

    parts.append(
        f"[{current}][sci]overlay=eval=frame:x='{sci_x}':y={y_pos}:enable='{_enable(sci_segs)}'[v1]"
    )
    parts.append(
        f"[v1][vil]overlay=eval=frame:x='{vil_x}':y={y_pos}:enable='{_enable(vil_segs)}'[v2]"
    )
    parts.append(f"[v2]ass={ffmpeg_ass_path}[vout]")
    parts.append(f"[1:a][4:a]amix=inputs=2:duration=first:weights=1 0.18[aout]")

    return ";".join(parts)


def _run_ffmpeg(cmd: List[str]) -> None:
    """Run an FFmpeg command list.  Raises RuntimeError on non-zero exit."""
    logger.debug("FFmpeg command: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg exited {result.returncode}: {result.stderr.decode(errors='replace')}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compose_video(
    background_path: str,
    audio_path: str,
    captions: List[Dict[str, Any]],
    output_path: str,
    resolution: Tuple[int, int] = (1080, 1920),
    media_inserts: List[Dict[str, Any]] = None,
) -> str:
    """
    Compose the final MP4 with background video, voiceover, and burned captions.

    Parameters
    ----------
    background_path : str
        Path to the background MP4 (looped if shorter than audio).
    audio_path : str
        Path to the WAV voiceover.
    captions : list
        Caption chunks from group_into_caption_chunks().
    output_path : str
        Destination MP4 path.
    resolution : tuple
        (width, height) – default (1080, 1920) for portrait TikTok.
    media_inserts : list, optional
        Timed image overlays from fetch_media_inserts().  Each entry is a
        dict with keys "path" (str), "start" (float), "end" (float).
        Images are shown in the upper ~42 % of the frame above the
        character sprites.

    Returns
    -------
    str
        *output_path* on success.

    Raises
    ------
    ValueError
        On invalid inputs (empty captions, bad resolution).
    VideoComposerError
        On FFmpeg failure.
    """
    # --- input validation ---
    if not captions:
        raise ValueError("captions list must not be empty.")
    width, height = resolution
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid resolution {resolution}: both dimensions must be > 0.")

    # --- write ASS subtitle file to output dir (avoids spaces/backslashes in temp paths) ---
    ass_content = _build_ass_subtitles(captions, resolution=resolution)
    ass_path = os.path.join(config.OUTPUT_DIR, "subtitles.ass")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    try:
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        # ffmpeg filter requires forward slashes; colons after drive letter must be escaped
        ffmpeg_ass_path = ass_path.replace("\\", "/").replace(":", "\\:")

        # --- pick a random start within the background video ---
        audio_duration = captions[-1]["end_time"]
        try:
            video_duration = _probe_duration(background_path)
            max_start = max(0.0, video_duration - audio_duration)
            start_time = random.uniform(0, max_start)
        except Exception as exc:
            logger.warning("Could not probe video duration: %s", exc)
            start_time = 0.0
            video_duration = 0.0

        needs_loop = video_duration > 0 and (start_time + audio_duration) > video_duration
        loop_args = ["-stream_loop", "-1"] if needs_loop else []

        # --- load speaker timings sidecar (written by elevenlabs TTS) ---
        timings_path = audio_path.replace(".wav", "_timings.json")
        timings = []
        if os.path.isfile(timings_path):
            with open(timings_path) as f:
                timings = json.load(f)

        # --- build FFmpeg command ---
        if timings:
            pop_path = _generate_pop_track(timings, audio_duration)
            inserts = media_inserts or []
            filter_complex = _build_filter_complex(
                timings, width, height, ffmpeg_ass_path, inserts
            )
            # Static images need -loop 1 applied per-input (before each -i)
            # Videos are added as plain inputs (no -loop 1)
            insert_inputs: List[str] = []
            for ins in inserts:
                if ins.get("kind", "image") == "video":
                    insert_inputs.extend(["-i", ins["path"]])
                else:
                    insert_inputs.extend(["-loop", "1", "-i", ins["path"]])
            cmd = [
                config.FFMPEG_PATH, "-y",
                *loop_args,
                "-ss", f"{start_time:.3f}",
                "-i", background_path,
                "-i", audio_path,
                "-i", _CHAR_IMAGES["SCIENTIST"],
                "-i", _CHAR_IMAGES["VILLAGER"],
                "-i", pop_path,
                *insert_inputs,
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-crf", str(config.VIDEO_CRF),
                "-r", str(config.VIDEO_FPS),
                "-c:a", "aac",
                "-b:a", config.AUDIO_BITRATE,
                "-shortest",
                output_path,
            ]
        else:
            cmd = [
                config.FFMPEG_PATH, "-y",
                *loop_args,
                "-ss", f"{start_time:.3f}",
                "-i", background_path,
                "-i", audio_path,
                "-vf", (
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                    f"ass={ffmpeg_ass_path}"
                ),
                "-c:v", "libx264",
                "-crf", str(config.VIDEO_CRF),
                "-r", str(config.VIDEO_FPS),
                "-c:a", "aac",
                "-b:a", config.AUDIO_BITRATE,
                "-shortest",
                output_path,
            ]

        try:
            _run_ffmpeg(cmd)
        except Exception as exc:
            raise VideoComposerError(f"Video composition failed: {exc}") from exc

    finally:
        # Clean up temp ASS file
        if os.path.exists(ass_path):
            try:
                os.unlink(ass_path)
            except OSError:
                pass

    return output_path
