"""
pipeline.uploader.instagram
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Upload a vertical MP4 as an Instagram Reel via instagrapi.

Required .env keys
------------------
INSTAGRAM_USERNAME
INSTAGRAM_PASSWORD

The session is cached in instagram_session.json so subsequent runs
skip the full login round-trip.
"""

import logging
import os
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_SESSION_FILE = "instagram_session.json"
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    try:
        from instagrapi import Client
        from instagrapi.exceptions import LoginRequired, BadPassword, ChallengeRequired
    except ImportError as exc:
        raise RuntimeError(
            "instagrapi is not installed. Run: pip install instagrapi"
        ) from exc

    cl = Client()
    cl.delay_range = [2, 5]  # polite request pacing

    if os.path.isfile(_SESSION_FILE):
        try:
            cl.load_settings(_SESSION_FILE)
            cl.login(config.INSTAGRAM_USERNAME, config.INSTAGRAM_PASSWORD)
            _client = cl
            return _client
        except (LoginRequired, Exception):
            logger.warning("Cached Instagram session invalid — re-authenticating.")
            cl = Client()
            cl.delay_range = [2, 5]

    cl.login(config.INSTAGRAM_USERNAME, config.INSTAGRAM_PASSWORD)
    cl.dump_settings(_SESSION_FILE)
    _client = cl
    return _client


def upload_to_instagram(video_path: str, caption: str) -> str:
    """Upload *video_path* as an Instagram Reel. Returns the media PK string."""
    cl    = _get_client()
    media = cl.clip_upload(Path(video_path), caption=caption)
    pk    = str(media.pk)
    logger.info("Instagram Reel live: pk=%s", pk)
    return pk
