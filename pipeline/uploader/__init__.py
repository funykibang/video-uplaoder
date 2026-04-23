"""
pipeline.uploader
~~~~~~~~~~~~~~~~~
Upload the finished MP4 to YouTube Shorts, Instagram Reels, and TikTok.

Public API
----------
upload_to_all(video_path, article, platforms=None) -> dict
    platforms defaults to all three.  Pass a subset list to skip platforms.
    Returns {"youtube": id_or_None, "instagram": id_or_None, "tiktok": id_or_None}.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_ALL_PLATFORMS = ("youtube", "instagram", "tiktok")


def upload_to_all(
    video_path: str,
    article: dict,
    platforms: Optional[list[str]] = None,
) -> dict[str, Optional[str]]:
    """
    Upload *video_path* to every platform in *platforms* (default: all three).

    Returns a dict mapping platform name → uploaded ID/URL (or None on failure).
    Never raises — failures are logged as errors so the pipeline keeps running.
    """
    if platforms is None:
        platforms = list(_ALL_PLATFORMS)

    title   = article.get("title", "Tech News")
    caption = _build_caption(article)
    results: dict[str, Optional[str]] = {}

    if "youtube" in platforms:
        results["youtube"] = _try_upload("youtube", _upload_youtube, video_path, title, caption)

    if "instagram" in platforms:
        results["instagram"] = _try_upload("instagram", _upload_instagram, video_path, caption)

    if "tiktok" in platforms:
        results["tiktok"] = _try_upload("tiktok", _upload_tiktok, video_path, title, caption)

    logger.info("Upload results: %s", results)
    return results


def _try_upload(platform: str, fn, *args) -> Optional[str]:
    try:
        result = fn(*args)
        logger.info("%s upload succeeded: %s", platform, result)
        return result
    except Exception as exc:
        logger.error("%s upload failed: %s", platform, exc)
        return None


def _build_caption(article: dict) -> str:
    title  = article.get("title", "")
    source = article.get("source", "")
    return f"{title}\n\nSource: {source}\n\n#TechNews #Shorts #AI"


def _upload_youtube(video_path: str, title: str, caption: str) -> str:
    from pipeline.uploader.youtube import upload_to_youtube
    return upload_to_youtube(video_path, title, caption)


def _upload_instagram(video_path: str, caption: str) -> str:
    from pipeline.uploader.instagram import upload_to_instagram
    return upload_to_instagram(video_path, caption)


def _upload_tiktok(video_path: str, title: str, caption: str) -> str:
    from pipeline.uploader.tiktok import upload_to_tiktok
    return upload_to_tiktok(video_path, title, caption)
