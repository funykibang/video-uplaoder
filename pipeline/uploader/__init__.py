"""
pipeline.uploader
~~~~~~~~~~~~~~~~~
Upload the finished MP4 via upload_post (UploadPostClient).

Required .env keys
------------------
UPLOAD_POST_API_KEY  – API key from upload-post dashboard
UPLOAD_POST_USER     – profile user created in the managed users page

Public API
----------
upload_to_all(video_path, article, platforms=None) -> dict
    platforms defaults to ["tiktok", "instagram"].
    Returns {"tiktok": response_or_None, "instagram": response_or_None, ...}.
"""

import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)

_ALL_PLATFORMS = ["tiktok", "instagram", "youtube"]


def upload_to_all(
    video_path: str,
    article: dict,
    platforms: Optional[list[str]] = None,
) -> dict[str, Optional[str]]:
    """
    Upload *video_path* to all platforms in *platforms* (default: tiktok + instagram).

    Returns a dict mapping platform name → result string (or None on failure).
    Never raises — failures are logged as errors so the pipeline keeps running.
    """
    if platforms is None:
        platforms = list(_ALL_PLATFORMS)

    title   = article.get("title", "Tech News")
    caption = _build_caption(article)

    try:
        from upload_post import UploadPostClient
    except ImportError as exc:
        raise RuntimeError(
            "upload_post is not installed. Run: pip install upload-post"
        ) from exc

    client = UploadPostClient(api_key=config.UPLOAD_POST_API_KEY)

    results: dict[str, Optional[str]] = {p: None for p in platforms}
    try:
        response = client.upload_video(
            video_path=video_path,
            title=title,
            user=config.UPLOAD_POST_USER,
            platforms=platforms,
        )
        if isinstance(response, dict) and response.get("success"):
            # Async upload — job handed off to background worker
            job_ref = response.get("request_id") or response.get("job_id") or "queued"
            for p in platforms:
                results[p] = job_ref
            logger.info(
                "Upload queued for %d platform(s). request_id=%s job_id=%s",
                response.get("total_platforms", len(platforms)),
                response.get("request_id"),
                response.get("job_id"),
            )
        elif isinstance(response, dict):
            for p in platforms:
                results[p] = str(response.get(p)) if response.get(p) is not None else None
            logger.info("Upload response: %s", response)
        else:
            for p in platforms:
                results[p] = str(response) if response is not None else None
            logger.info("Upload response: %s", response)
    except Exception as exc:
        logger.error("upload_post upload failed: %s", exc)

    return results


def _build_caption(article: dict) -> str:
    title  = article.get("title", "")
    source = article.get("source", "")
    return f"{title}\n\nSource: {source}\n\n#TechNews #Shorts #AI"
