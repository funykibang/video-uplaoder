"""
pipeline.media_fetcher
~~~~~~~~~~~~~~~~~~~~~~
Fetches visual media inserts for the video overlay:
  - Article hero image (top_image from newspaper3k)
  - Stock photos from the Pexels Photos API
  - Stock video clips from the Pexels Videos API

Public API
----------
fetch_media_inserts(article, audio_duration, output_dir) -> list[dict]
    Returns a list of {"path": str, "start": float, "end": float,
    "kind": "image"|"video"}, one entry per asset, scheduled to appear
    for MEDIA_INSERT_SHOW_DURATION seconds each with a MEDIA_INSERT_GAP
    gap between them.
"""

import logging
import os
import urllib.request

import requests

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _download(url: str, dest: str) -> bool:
    """Download *url* to *dest*. Returns True on success."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; VideoUploader/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
            data = resp.read()
        with open(dest, "wb") as fh:
            fh.write(data)
        return True
    except Exception as exc:
        logger.warning("Could not download %s: %s", url, exc)
        return False


def _fetch_article_image(article: dict, output_dir: str) -> str | None:
    """
    Download the article's hero image (article["top_image"]).
    Returns the local file path on success, or None if unavailable.
    """
    img_url = article.get("top_image", "").strip()
    if not img_url:
        return None

    ext = os.path.splitext(img_url.split("?")[0])[-1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        ext = ".jpg"
    dest = os.path.join(output_dir, f"article_hero{ext}")
    if _download(img_url, dest):
        logger.info("Article hero image saved: %s", dest)
        return dest
    return None


def _fetch_pexels_images(
    query: str, count: int, output_dir: str, file_prefix: str = "stock"
) -> list[str]:
    """
    Search Pexels for *count* portrait-oriented stock photos matching *query*.
    Returns a list of local file paths for successfully downloaded images.
    Silently returns [] if PEXELS_API_KEY is not set or the request fails.
    """
    if not config.PEXELS_API_KEY:
        logger.warning("PEXELS_API_KEY not configured — skipping stock images.")
        return []

    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": config.PEXELS_API_KEY},
            params={"query": query, "per_page": count, "orientation": "portrait"},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Pexels API error: %s", exc)
        return []

    paths = []
    for i, photo in enumerate(resp.json().get("photos", [])[:count]):
        src = photo.get("src", {})
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url:
            continue
        dest = os.path.join(output_dir, f"{file_prefix}_{i}.jpg")
        if _download(url, dest):
            paths.append(dest)

    logger.info("Downloaded %d Pexels stock images for query %r.", len(paths), query)
    return paths


def _fetch_pexels_videos(
    query: str, count: int, output_dir: str, file_prefix: str = "stock_vid"
) -> list[str]:
    """
    Search Pexels for *count* portrait-oriented stock video clips matching *query*.
    Prefers HD quality; falls back to SD.  Returns local file paths.
    Silently returns [] if PEXELS_API_KEY is not set or the request fails.
    """
    if not config.PEXELS_API_KEY:
        logger.warning("PEXELS_API_KEY not configured — skipping stock videos.")
        return []

    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": config.PEXELS_API_KEY},
            params={"query": query, "per_page": count, "orientation": "portrait"},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Pexels Videos API error: %s", exc)
        return []

    paths = []
    for i, video in enumerate(resp.json().get("videos", [])[:count]):
        files = video.get("video_files", [])
        # Prefer hd portrait, fall back to sd, then any
        chosen = None
        for quality in ("hd", "sd", ""):
            for vf in files:
                if (not quality or vf.get("quality") == quality) and vf.get("link"):
                    chosen = vf["link"]
                    break
            if chosen:
                break
        if not chosen:
            continue
        dest = os.path.join(output_dir, f"{file_prefix}_{i}.mp4")
        if _download(chosen, dest):
            paths.append(dest)

    logger.info("Downloaded %d Pexels stock videos for query %r.", len(paths), query)
    return paths


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_media_inserts(
    article: dict,
    audio_duration: float,
    output_dir: str,
    script: str | None = None,
    timings: list | None = None,
) -> list[dict]:
    """
    Build a list of timed media inserts for the video overlay.

    When *script* and *timings* are supplied the inserts are contextually
    matched to what the SCIENTIST is discussing at each moment: Ollama
    generates a 2-4 word Pexels query per SCIENTIST segment and one
    image or video is fetched per segment.

    When *script*/*timings* are absent (or Ollama fails entirely) the
    function falls back to the original behaviour: fetch generic stock
    content based on the article title.

    The RSS thumbnail (if present) is always pinned as the very first
    insert at t=1.0 s regardless of mode.
    """
    os.makedirs(output_dir, exist_ok=True)

    show_dur = getattr(config, "MEDIA_INSERT_SHOW_DURATION", 3.5)
    gap      = getattr(config, "MEDIA_INSERT_GAP", 1.0)

    inserts: list[dict] = []

    # ── 0 ── RSS thumbnail pinned at t=1.0 s ────────────────────────────────
    thumbnail_url = article.get("thumbnail", "").strip()
    thumb_end = 0.0
    if thumbnail_url:
        ext = os.path.splitext(thumbnail_url.split("?")[0])[-1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = ".jpg"
        dest = os.path.join(output_dir, f"rss_thumbnail{ext}")
        if _download(thumbnail_url, dest):
            logger.info("RSS thumbnail saved: %s", dest)
            thumb_end = 1.0 + show_dur
            if thumb_end <= audio_duration:
                inserts.append({"path": dest, "start": 1.0, "end": thumb_end, "kind": "image"})

    # ── 1 ── Script-driven mode: one contextual insert per SCIENTIST line ────
    if script and timings:
        from pipeline.script_writer import generate_visual_queries
        visual_segments = generate_visual_queries(script, timings)
        for seg_idx, seg in enumerate(visual_segments):
            start = seg["start"]
            # Show the insert for the duration of the segment, capped at show_dur
            clip_dur = min(seg["end"] - start, show_dur)
            clip_dur = max(clip_dur, 1.0)  # at least 1 s
            end = start + clip_dur

            # Skip if it overlaps with the thumbnail window
            if start < thumb_end:
                continue
            if end > audio_duration:
                break

            query = seg["query"]
            prefix = f"seg{seg_idx}"
            # Alternate image → video → image … for visual variety
            if seg_idx % 2 == 0:
                paths = _fetch_pexels_images(query, count=1, output_dir=output_dir, file_prefix=prefix)
                kind  = "image"
                if not paths:
                    paths = _fetch_pexels_videos(query, count=1, output_dir=output_dir, file_prefix=prefix)
                    kind  = "video"
            else:
                paths = _fetch_pexels_videos(query, count=1, output_dir=output_dir, file_prefix=prefix)
                kind  = "video"
                if not paths:
                    paths = _fetch_pexels_images(query, count=1, output_dir=output_dir, file_prefix=prefix)
                    kind  = "image"

            if paths:
                inserts.append({"path": paths[0], "start": start, "end": end, "kind": kind})
                logger.debug("  insert[%d] %s query=%r %.1f-%.1f s", seg_idx, kind, query, start, end)

    # ── 2 ── Fallback mode: generic stock content based on article title ──────
    else:
        cursor = (inserts[-1]["end"] + gap) if inserts else (1.0 + show_dur + gap)
        assets: list[tuple[str, str]] = []

        # Article hero image (only when no RSS thumbnail)
        if not thumbnail_url:
            hero = _fetch_article_image(article, output_dir)
            if hero:
                assets.append((hero, "image"))

        query    = " ".join(article.get("title", "technology").split()[:5])
        n_images = getattr(config, "PEXELS_IMAGES_COUNT", 2)
        n_videos = getattr(config, "PEXELS_VIDEOS_COUNT", 2)

        for p in _fetch_pexels_images(query, count=n_images, output_dir=output_dir):
            assets.append((p, "image"))
        for p in _fetch_pexels_videos(query, count=n_videos, output_dir=output_dir):
            assets.append((p, "video"))

        for path, kind in assets:
            end = cursor + show_dur
            if end > audio_duration:
                break
            inserts.append({"path": path, "start": cursor, "end": end, "kind": kind})
            cursor = end + gap

    logger.info(
        "Scheduled %d media insert(s) (%d image, %d video) over %.1f s of audio.",
        len(inserts),
        sum(1 for x in inserts if x["kind"] == "image"),
        sum(1 for x in inserts if x["kind"] == "video"),
        audio_duration,
    )
    return inserts
