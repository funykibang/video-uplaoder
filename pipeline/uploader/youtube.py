"""
pipeline.uploader.youtube
~~~~~~~~~~~~~~~~~~~~~~~~~
Upload a vertical MP4 as a YouTube Short using the YouTube Data API v3.

Required .env keys
------------------
YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN

One-time setup
--------------
Run `python -m pipeline.uploader.youtube --auth` to complete the OAuth2
flow and print your refresh token.  Paste it into .env.
"""

import argparse
import logging
import os
import sys

import config

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _build_credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    creds = Credentials(
        token=None,
        refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        scopes=_SCOPES,
    )
    creds.refresh(Request())
    return creds


def upload_to_youtube(video_path: str, title: str, description: str = "") -> str:
    """Upload *video_path* as a YouTube Short. Returns the video ID."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds   = _build_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title":       f"{title} #Shorts",
            "description": description,
            "categoryId":  "28",  # Science & Technology
            "tags":        ["shorts", "technews", "ai", "tech"],
        },
        "status": {
            "privacyStatus":            "public",
            "selfDeclaredMadeForKids":  False,
        },
    }

    media   = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.debug("YouTube upload: %d%%", int(status.progress() * 100))

    video_id = response["id"]
    logger.info("YouTube Short live: https://youtube.com/shorts/%s", video_id)
    return video_id


# ---------------------------------------------------------------------------
# One-time auth helper: python -m pipeline.uploader.youtube --auth
# ---------------------------------------------------------------------------

def _run_auth_flow():
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id":                  config.YOUTUBE_CLIENT_ID,
            "client_secret":              config.YOUTUBE_CLIENT_SECRET,
            "auth_uri":                   "https://accounts.google.com/o/oauth2/auth",
            "token_uri":                  "https://oauth2.googleapis.com/token",
            "redirect_uris":              ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }
    flow  = InstalledAppFlow.from_client_config(client_config, _SCOPES)
    creds = flow.run_local_server(port=0)
    print("\nYOUR REFRESH TOKEN (add to .env as YOUTUBE_REFRESH_TOKEN):")
    print(creds.refresh_token)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth", action="store_true", help="Run OAuth2 flow to get refresh token")
    args = parser.parse_args()
    if args.auth:
        logging.basicConfig(level=logging.INFO)
        _run_auth_flow()
    else:
        parser.print_help()
        sys.exit(1)
