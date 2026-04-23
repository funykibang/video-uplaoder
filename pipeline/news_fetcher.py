"""
pipeline.news_fetcher
~~~~~~~~~~~~~~~~~~~~~
Fetches the latest unseen tech article from configured RSS feeds.

Public API
----------
fetch_latest_news(feed_urls=None) -> dict
    Returns a dict with keys: title, source, summary, full_text, url.

Private helpers (also importable for unit-testing via mock.patch)
-----------------------------------------------------------------
_fetch_full_text(url) -> str
_is_seen(url) -> bool
_mark_seen(url) -> None
_get_db_conn() -> sqlite3.Connection
"""

import csv
import datetime
import os
import sqlite3
import logging
from typing import Optional

import feedparser  # type: ignore
import requests  # type: ignore
from bs4 import BeautifulSoup  # type: ignore

try:
    import cloudscraper  # type: ignore
    _scraper = cloudscraper.create_scraper()
except ImportError:  # pragma: no cover
    _scraper = None  # type: ignore

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class NoNewArticlesError(RuntimeError):
    """Raised when no unseen article can be found across all feeds."""


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

_db_conn: Optional[sqlite3.Connection] = None


def _get_db_conn() -> sqlite3.Connection:
    """Return a module-level singleton SQLite connection (lazy init)."""
    global _db_conn
    if _db_conn is None:
        _db_conn = sqlite3.connect(config.DEDUP_DB_PATH)
        _db_conn.execute(
            """CREATE TABLE IF NOT EXISTS seen_articles (
                url      TEXT PRIMARY KEY,
                seen_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        _db_conn.commit()
    return _db_conn


def _is_seen(url: str) -> bool:
    """Return True if *url* is already in the de-dup table."""
    conn = _get_db_conn()
    row = conn.execute("SELECT 1 FROM seen_articles WHERE url = ?", (url,)).fetchone()
    return row is not None


def _mark_seen(url: str) -> None:
    """Insert *url* into the de-dup table (silently ignores duplicates)."""
    conn = _get_db_conn()
    conn.execute("INSERT OR IGNORE INTO seen_articles (url) VALUES (?)", (url,))
    conn.commit()


# ---------------------------------------------------------------------------
# CSV video log helpers
# ---------------------------------------------------------------------------

_CSV_COLUMNS = ["date", "title", "source", "url", "video_path"]


def _is_video_made(url: str) -> bool:
    """Return True if *url* already has a row in the videos log CSV."""
    path = config.VIDEOS_LOG_PATH
    if not os.path.isfile(path):
        return False
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if row.get("url", "").strip() == url.strip():
                    return True
    except Exception as exc:
        logger.warning("Could not read videos log CSV: %s", exc)
    return False


def log_video_made(article: dict, video_path: str) -> None:
    """
    Append one row to the videos log CSV recording that a video was
    successfully produced for *article*.

    Creates the file (with header) if it does not yet exist.
    """
    path = config.VIDEOS_LOG_PATH
    write_header = not os.path.isfile(path)
    try:
        with open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_CSV_COLUMNS)
            if write_header:
                writer.writeheader()
            writer.writerow({
                "date":       datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "title":      article.get("title", ""),
                "source":     article.get("source", ""),
                "url":        article.get("url", ""),
                "video_path": os.path.abspath(video_path),
            })
        logger.info("Video log updated: %s", path)
    except Exception as exc:
        logger.warning("Could not write to videos log CSV: %s", exc)


# ---------------------------------------------------------------------------
# Full-text extraction
# ---------------------------------------------------------------------------

try:
    from newspaper import Article  # type: ignore
    from newspaper import Config as NewspaperConfig  # type: ignore
except ImportError:  # pragma: no cover
    Article = None  # type: ignore
    NewspaperConfig = None  # type: ignore

try:
    import trafilatura  # type: ignore
except ImportError:  # pragma: no cover
    trafilatura = None  # type: ignore

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _extract_thumbnail(entry) -> str:
    """Try multiple RSS fields to extract a thumbnail URL."""

    # 1. media_content
    media = getattr(entry, "media_content", None)
    if media and isinstance(media, list):
        url = media[0].get("url")
        if url:
            return url

    # 2. media_thumbnail
    thumb = getattr(entry, "media_thumbnail", None)
    if thumb and isinstance(thumb, list):
        url = thumb[0].get("url")
        if url:
            return url

    # 3. links
    for link in getattr(entry, "links", []):
        if getattr(link, "type", "").startswith("image"):
            return link.href

    # 4. summary HTML fallback
    summary = getattr(entry, "summary", "")
    if summary:
        soup = BeautifulSoup(summary, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]

    return ""


def _fetch_article_top_image(url: str) -> str:
    """Return the hero/top image URL for *url* via newspaper3k, or empty string."""
    if Article is None or NewspaperConfig is None:
        return ""
    try:
        np_cfg = NewspaperConfig()
        np_cfg.browser_user_agent = _BROWSER_HEADERS["User-Agent"]
        np_cfg.request_timeout = 15
        art = Article(url, config=np_cfg)
        art.download()
        art.parse()
        return art.top_image or ""
    except Exception:
        return ""


def _get_html(url: str) -> str:
    """Fetch raw HTML, trying cloudscraper first then plain requests."""
    if _scraper is not None:
        try:
            resp = _scraper.get(url, timeout=20)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            logger.debug("cloudscraper fetch failed for %s: %s", url, exc)

    resp = requests.get(url, headers=_BROWSER_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def _fetch_full_text(url: str) -> str:
    """
    Try trafilatura (via cloudscraper HTML fetch) first, then newspaper3k.
    Returns empty string if both fail.
    """
    # --- trafilatura via cloudscraper ---
    if trafilatura is not None:
        try:
            html = _get_html(url)
            text = trafilatura.extract(html)
            if text:
                return text
            logger.debug("trafilatura returned empty for %s", url)
        except Exception as exc:
            logger.warning("trafilatura/fetch failed for %s: %s", url, exc)

    # --- newspaper3k fallback ---
    if Article is not None and NewspaperConfig is not None:
        try:
            np_cfg = NewspaperConfig()
            np_cfg.browser_user_agent = _BROWSER_HEADERS["User-Agent"]
            np_cfg.request_timeout = 15
            article = Article(url, config=np_cfg)
            article.download()
            article.parse()
            if article.text:
                return article.text
            logger.debug("newspaper3k returned empty for %s", url)
        except Exception as exc:
            logger.warning("newspaper3k failed for %s: %s", url, exc)

    logger.warning("Full-text extraction failed for %s — script will use RSS summary only.", url)
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_candidate_articles(n: int = 10, feed_urls=None) -> list[dict]:
    """
    Collect up to *n* unseen articles across all feeds WITHOUT marking them
    as seen.  The caller is responsible for calling _mark_seen() on whichever
    article it actually uses.

    Returns a list of article dicts (same shape as fetch_latest_news).
    Raises NoNewArticlesError if fewer than 1 candidate is found.
    """
    if feed_urls is None:
        feed_urls = config.RSS_FEEDS

    candidates: list[dict] = []

    for feed_url in feed_urls:
        if len(candidates) >= n:
            break
        try:
            feed = feedparser.parse(feed_url)
        except Exception as exc:
            logger.warning("Failed to parse feed %s: %s", feed_url, exc)
            continue

        if feed.bozo and not feed.entries:
            logger.warning("Malformed (bozo) feed, skipping: %s", feed_url)
            continue

        for entry in feed.entries:
            if len(candidates) >= n:
                break
            url = getattr(entry, "link", "")
            if not url or _is_seen(url) or _is_video_made(url):
                continue

            title   = getattr(entry, "title",   "")
            summary = getattr(entry, "summary", "")
            source  = _source_from_url(feed_url)

            candidates.append({
                "title":     title,
                "source":    source,
                "summary":   summary,
                "full_text": "",   # fetched lazily only for the chosen article
                "url":       url,
                "thumbnail": _extract_thumbnail(entry),
                "top_image": "",
            })

    if not candidates:
        raise NoNewArticlesError("No candidate articles found across the provided feeds.")

    logger.info("Collected %d candidate article(s) for ranking.", len(candidates))
    return candidates


def hydrate_article(article: dict) -> dict:
    """
    Fetch full_text and top_image for a candidate article dict (in-place + return).
    Also marks the URL as seen.
    """
    url = article["url"]
    article["full_text"] = _fetch_full_text(url)
    if not article["thumbnail"]:
        article["top_image"] = _fetch_article_top_image(url)
    _mark_seen(url)
    return article


def fetch_latest_news(feed_urls=None) -> dict:
    """
    Iterate over *feed_urls* (defaults to config.RSS_FEEDS), return the first
    unseen article as a dict with keys: title, source, summary, full_text, url.

    Raises NoNewArticlesError if every article across all feeds has been seen
    already, or if all feeds are empty / unreachable.
    """
    if feed_urls is None:
        feed_urls = config.RSS_FEEDS

    for feed_url in feed_urls:
        try:
            feed = feedparser.parse(feed_url)
        except Exception as exc:
            logger.warning("Failed to parse feed %s: %s", feed_url, exc)
            continue

        if feed.bozo and not feed.entries:
            logger.warning("Malformed (bozo) feed, skipping: %s", feed_url)
            continue

        for entry in feed.entries:
            url = getattr(entry, "link", "")
            if not url:
                continue
            if _is_seen(url):
                continue

            # Found an unseen article
            title     = getattr(entry, "title",   "")
            summary   = getattr(entry, "summary", "")
            source    = _source_from_url(feed_url)
            full_text = _fetch_full_text(url)
            thumbnail = _extract_thumbnail(entry)
            top_image = _fetch_article_top_image(url) if not thumbnail else ""

            _mark_seen(url)

            return {
                "title":     title,
                "source":    source,
                "summary":   summary,
                "full_text": full_text,
                "url":       url,
                "thumbnail": thumbnail,
                "top_image": top_image,
            }

    raise NoNewArticlesError(
        "No new articles found across the provided feeds."
    )


def _source_from_url(feed_url: str) -> str:
    """Derive a human-readable source name from the feed URL."""
    mapping = {
        "arstechnica": "Ars Technica",
        "techcrunch":  "TechCrunch",
        "theverge":    "The Verge",
        "hnrss":       "Hacker News",
    }
    for key, name in mapping.items():
        if key in feed_url:
            return name
    return feed_url
