"""
pipeline.background_source
~~~~~~~~~~~~~~~~~~~~~~~~~~
Resolves a background video file for the composition step.

Public API
----------
get_background_video(duration: float) -> str
    Picks a random MP4 from assets/backgrounds/ and returns its path.

Raises BackgroundSourceError if no background videos are found.
"""

import logging
import os
import random

import config

logger = logging.getLogger(__name__)


class BackgroundSourceError(RuntimeError):
    """Raised when no background video can be obtained."""


def get_background_video(duration: float, category: str = "satisfying") -> str:
    bg_dir = os.path.join(config.ASSETS_DIR, "backgrounds")
    videos = [
        os.path.join(bg_dir, f)
        for f in os.listdir(bg_dir)
        if f.lower().endswith(".mp4")
    ] if os.path.isdir(bg_dir) else []

    if not videos:
        raise BackgroundSourceError(
            f"No background videos found in {bg_dir}. "
            "Add MP4 files to assets/backgrounds/."
        )

    chosen = random.choice(videos)
    logger.info("Using background: %s", chosen)
    return chosen
