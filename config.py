"""
Central configuration for the Video Uploader pipeline.
All tuneable constants live here so every module imports from one place.
"""

import os
import shutil
from dotenv import load_dotenv
load_dotenv()

RSS_FEEDS = [
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://hnrss.org/newest?points=100",
]

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

OUTPUT_DIR = "output"
ASSETS_DIR = "assets"

_FFMPEG_WINGET  = r"C:\Users\juras\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe"
_FFPROBE_WINGET = r"C:\Users\juras\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffprobe.exe"
FFMPEG_PATH  = _FFMPEG_WINGET  if os.path.isfile(_FFMPEG_WINGET)  else (shutil.which("ffmpeg")  or "ffmpeg")
FFPROBE_PATH = _FFPROBE_WINGET if os.path.isfile(_FFPROBE_WINGET) else (shutil.which("ffprobe") or "ffprobe")

BACKGROUND_VIDEO     = os.environ.get("BACKGROUND_VIDEO", "")
BACKGROUND_VIDEO_URL = os.environ.get("BACKGROUND_VIDEO_URL", "")

TTS_ENGINE = "elevenlabs"  # or "piper" / "coqui"
PIPER_MODEL = "assets/voices/en_US-lessac-medium.onnx"

ELEVENLABS_API_KEY           = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_MODEL             = "eleven_turbo_v2"
ELEVENLABS_SCIENTIST_VOICE   = "s9Uwhs8odVx1Fz7IbkbF"
ELEVENLABS_VILLAGER_VOICE    = "904GxMGdESbkMtNiWylt"
PEXELS_API_KEY               = os.environ.get("PEXELS_API_KEY", "")

# SQLite database used for article de-duplication
DEDUP_DB_PATH = "dedup.db"

# CSV log of every article that successfully became a finished video
VIDEOS_LOG_PATH = "videos_log.csv"

# TTS audio settings
TTS_SAMPLE_RATE = 22050
TTS_BIT_DEPTH = 16

# Script validation limits
SCRIPT_MIN_WORDS = 180
SCRIPT_MAX_WORDS = 350
SCRIPT_HOOK_MAX_WORDS = 20
SCRIPT_MAX_RETRIES = 5

# Video output settings
VIDEO_RESOLUTION = (1080, 1920)
VIDEO_FPS = 30
VIDEO_CRF = 18
AUDIO_BITRATE = "192k"

# Caption settings
CAPTION_CHUNK_SIZE = 4  # words per on-screen caption chunk
CAPTION_FONT = "Montserrat-Bold"
CAPTION_FONT_SIZE = 72
CAPTION_PRIMARY_COLOUR = "&H00FFFFFF"   # white
CAPTION_OUTLINE_COLOUR = "&H00000000"   # black stroke
CAPTION_HIGHLIGHT_COLOUR = "&H0000FFFF" # yellow word highlight

# Media insert settings (article screenshot + stock photos/videos)
MEDIA_INSERT_SHOW_DURATION = 3.5   # seconds each asset is displayed
MEDIA_INSERT_GAP = 1.0             # gap in seconds between consecutive inserts
PEXELS_IMAGES_COUNT = 2            # number of Pexels stock photos to fetch
PEXELS_VIDEOS_COUNT = 2            # number of Pexels stock video clips to fetch

# ---------------------------------------------------------------------------
# Scheduler – times the server fires the pipeline each day (server local time)
# ---------------------------------------------------------------------------
SCHEDULE_TIMES = os.environ.get("SCHEDULE_TIMES", "12:00,20:00").split(",")
CLEANUP_TIME   = os.environ.get("CLEANUP_TIME", "23:30")

# ---------------------------------------------------------------------------
# Upload credentials
# ---------------------------------------------------------------------------

# YouTube Data API v3
# One-time setup: python -m pipeline.uploader.youtube --auth
YOUTUBE_CLIENT_ID     = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")

# Instagram (via instagrapi)
INSTAGRAM_USERNAME = os.environ.get("INSTAGRAM_USERNAME", "")
INSTAGRAM_PASSWORD = os.environ.get("INSTAGRAM_PASSWORD", "")

# TikTok Content Posting API v2 (legacy – no longer used)
TIKTOK_CLIENT_KEY    = os.environ.get("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
TIKTOK_ACCESS_TOKEN  = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
TIKTOK_REFRESH_TOKEN = os.environ.get("TIKTOK_REFRESH_TOKEN", "")

# upload-post third-party uploader
UPLOAD_POST_API_KEY = os.environ.get("UPLOAD_POST_API_KEY", "")
UPLOAD_POST_USER    = os.environ.get("UPLOAD_POST_USER", "")
