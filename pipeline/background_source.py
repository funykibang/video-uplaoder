"""
pipeline.background_source
~~~~~~~~~~~~~~~~~~~~~~~~~~
Resolves a background video file for the composition step.

Public API
----------
get_background_video(duration: float, category="satisfying") -> str
    Returns an absolute path to a suitable background MP4.
    Picks randomly from assets/backgrounds/ if videos exist there;
    otherwise tries to download one from Pexels (if API key is set).

Raises BackgroundSourceError if no background can be obtained.
"""

import logging
import os
import random
import tempfile
from typing import Optional

import config

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class BackgroundSourceError(RuntimeError):
    """Raised when no background video can be obtained."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_local_backgrounds() -> list:
    """Return a list of MP4 file paths from the backgrounds asset directory."""
    bg_dir = os.path.join(config.ASSETS_DIR, "backgrounds")
    if not os.path.isdir(bg_dir):
        return []
    return [
        os.path.join(bg_dir, f)
        for f in os.listdir(bg_dir)
        if f.lower().endswith(".mp4")
    ]


def _download_from_pexels(duration: float, category: str) -> Optional[str]:
    """
    Download a random video from the Pexels API that matches *category*.
    Returns the path to the downloaded file, or None if the API key is not set
    or the download fails.
    """
    if not config.PEXELS_API_KEY:
        return None

    try:
        headers = {"Authorization": config.PEXELS_API_KEY}
        params  = {
            "query":    category,
            "per_page": 15,
            "min_duration": int(duration),
        }
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        if not videos:
            return None

        video = random.choice(videos)
        # Pick the highest-quality video file
        files = sorted(
            video.get("video_files", []),
            key=lambda vf: vf.get("width", 0),
            reverse=True,
        )
        if not files:
            return None

        video_url = files[0]["link"]
        dl_resp   = requests.get(video_url, timeout=120, stream=True)
        dl_resp.raise_for_status()

        fd, path = tempfile.mkstemp(suffix=".mp4",
                                    dir=os.path.join(config.ASSETS_DIR, "backgrounds"))
        with os.fdopen(fd, "wb") as f:
            for chunk in dl_resp.iter_content(chunk_size=65536):
                f.write(chunk)
        logger.info("Downloaded background video from Pexels: %s", path)
        return path

    except Exception as exc:
        logger.warning("Pexels download failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_background_video(duration: float, category: str = "satisfying") -> str:
    """
    Return the path to a background MP4 suitable for *duration* seconds.

    If BACKGROUND_VIDEO is set in config, that file is always used.
    Otherwise picks randomly from assets/backgrounds/, then falls back to Pexels.
    """
    if getattr(config, "BACKGROUND_VIDEO", None):
        path = config.BACKGROUND_VIDEO
        if not os.path.isfile(path):
            raise BackgroundSourceError(f"BACKGROUND_VIDEO not found: {path}")
        logger.info("Using fixed background: %s", path)
        return path

    local = _list_local_backgrounds()
    if local:
        chosen = random.choice(local)
        logger.info("Using local background: %s", chosen)
        return chosen

    pexels_path = _download_from_pexels(duration, category)
    if pexels_path:
        return pexels_path

    raise BackgroundSourceError(
        "No background videos found in assets/backgrounds/ and Pexels download failed "
        "(check PEXELS_API_KEY in config.py)."
    )
