"""
pipeline.uploader.tiktok
~~~~~~~~~~~~~~~~~~~~~~~~
Upload a vertical MP4 via TikTok Content Posting API v2.

Required .env keys
------------------
TIKTOK_CLIENT_KEY
TIKTOK_CLIENT_SECRET
TIKTOK_ACCESS_TOKEN    – obtained via OAuth2 flow (expires in 24 h)
TIKTOK_REFRESH_TOKEN   – used to obtain a new access token automatically

One-time setup
--------------
Complete the OAuth2 flow in TikTok's developer console to get an initial
access + refresh token pair, then add both to .env.  The uploader will
refresh the access token automatically before each upload.
"""

import json
import logging
import os

import requests

import config

logger = logging.getLogger(__name__)

_BASE      = "https://open.tiktokapis.com"
_TOKEN_URL = f"{_BASE}/v2/oauth/token/"
_INIT_URL  = f"{_BASE}/v2/post/publish/video/init/"

_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB


def _refresh_access_token() -> str:
    """Exchange the refresh token for a new access token. Returns the new token."""
    resp = requests.post(
        _TOKEN_URL,
        data={
            "client_key":     config.TIKTOK_CLIENT_KEY,
            "client_secret":  config.TIKTOK_CLIENT_SECRET,
            "grant_type":     "refresh_token",
            "refresh_token":  config.TIKTOK_REFRESH_TOKEN,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok token refresh failed: {data}")
    new_access  = data["access_token"]
    new_refresh = data.get("refresh_token", config.TIKTOK_REFRESH_TOKEN)
    logger.debug("TikTok token refreshed.")
    # Persist the new refresh token back to the env so in-process it stays current
    os.environ["TIKTOK_ACCESS_TOKEN"]  = new_access
    os.environ["TIKTOK_REFRESH_TOKEN"] = new_refresh
    return new_access


def upload_to_tiktok(video_path: str, title: str, caption: str = "") -> str:
    """
    Upload *video_path* as a TikTok post.
    Returns the publish_id string from TikTok's API.
    """
    access_token = _refresh_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json; charset=UTF-8",
    }

    video_size = os.path.getsize(video_path)
    chunk_size = min(_CHUNK_SIZE, video_size)
    total_chunks = (video_size + chunk_size - 1) // chunk_size

    # Step 1 – initialise upload
    init_payload = {
        "post_info": {
            "title":                   title[:150],
            "privacy_level":           "PUBLIC_TO_EVERYONE",
            "disable_duet":            False,
            "disable_comment":         False,
            "disable_stitch":          False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source":             "FILE_UPLOAD",
            "video_size":         video_size,
            "chunk_size":         chunk_size,
            "total_chunk_count":  total_chunks,
        },
    }
    resp = requests.post(_INIT_URL, headers=headers, json=init_payload, timeout=30)
    resp.raise_for_status()
    init_data = resp.json()

    if init_data.get("error", {}).get("code", "ok") != "ok":
        raise RuntimeError(f"TikTok init failed: {init_data}")

    publish_id = init_data["data"]["publish_id"]
    upload_url = init_data["data"]["upload_url"]

    # Step 2 – upload chunks
    with open(video_path, "rb") as fh:
        for chunk_index in range(total_chunks):
            chunk_data  = fh.read(chunk_size)
            start_byte  = chunk_index * chunk_size
            end_byte    = start_byte + len(chunk_data) - 1
            chunk_headers = {
                "Content-Type":   "video/mp4",
                "Content-Range":  f"bytes {start_byte}-{end_byte}/{video_size}",
                "Content-Length": str(len(chunk_data)),
            }
            put_resp = requests.put(
                upload_url,
                headers=chunk_headers,
                data=chunk_data,
                timeout=120,
            )
            put_resp.raise_for_status()
            logger.debug(
                "TikTok chunk %d/%d uploaded.", chunk_index + 1, total_chunks
            )

    logger.info("TikTok post submitted: publish_id=%s", publish_id)
    return publish_id
