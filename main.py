"""
main.py – TikTok / Reels video generation pipeline CLI.

Usage
-----
python main.py [--topic TEXT] [--batch N] [--tts-engine coqui|piper]
               [--llm-backend ollama]

Steps
-----
1. fetch     – Pull latest unseen tech article from RSS feeds
2. script    – Generate narration script via Ollama
3. tts       – Synthesise voiceover WAV
4. captions  – Extract word timestamps; group into caption chunks
5. background– Resolve background MP4
6. compose   – Burn captions + audio onto background → final MP4
"""

import argparse
import logging
import json
import os
import sys

import config
from pipeline import (
    fetch_latest_news,
    fetch_candidate_articles,
    hydrate_article,
    log_video_made,
    pick_best_article,
    generate_script,
    generate_voiceover,
    extract_word_timestamps,
    group_into_caption_chunks,
    compose_video,
    get_background_video,
    fetch_media_inserts,
)
from pipeline.news_fetcher import NoNewArticlesError
from pipeline.script_writer import ScriptGenerationError
from pipeline.tts_engine import TTSError
from pipeline.caption_sync import CaptionSyncError
from pipeline.video_composer import VideoComposerError
from pipeline.background_source import BackgroundSourceError
from pipeline.uploader import upload_to_all

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a TikTok/Reels video from the latest tech news."
    )
    parser.add_argument(
        "--topic",
        default=None,
        help="Optional keyword to filter RSS headlines (case-insensitive substring match).",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=1,
        metavar="N",
        help="Number of videos to produce in one run (default: 1).",
    )
    parser.add_argument(
        "--tts-engine",
        dest="tts_engine",
        choices=["coqui", "piper"],
        default=config.TTS_ENGINE,
        help="TTS engine to use (default: %(default)s).",
    )
    parser.add_argument(
        "--llm-backend",
        dest="llm_backend",
        choices=["ollama"],
        default="ollama",
        help="LLM backend for script generation (default: %(default)s).",
    )
    parser.add_argument(
        "--no-upload",
        dest="no_upload",
        action="store_true",
        help="Skip uploading to YouTube / Instagram / TikTok.",
    )
    parser.add_argument(
        "--platforms",
        default=None,
        help="Comma-separated subset of platforms to upload to (e.g. youtube,tiktok).",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(
    topic=None,
    tts_engine=None,
    llm_backend="ollama",
    output_dir=None,
) -> str:
    """
    Execute one full pipeline run and return the path to the output MP4.

    Parameters
    ----------
    topic : str | None
        Optional keyword; if the fetched article title/summary does not contain
        it, a NoNewArticlesError is raised to signal no match.
    tts_engine : str
        "coqui" or "piper".
    llm_backend : str
        Currently only "ollama".
    output_dir : str | None
        Directory for output files; defaults to config.OUTPUT_DIR.

    Returns
    -------
    tuple[str, dict]
        (absolute path to the composed MP4, article dict used for the video)
    """
    tts_engine  = tts_engine  or config.TTS_ENGINE
    output_dir  = output_dir  or config.OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    # -----------------------------------------------------------------------
    # Step 1 – Fetch & rank news
    # -----------------------------------------------------------------------
    logger.info("[1/7] Fetching candidate articles …")
    candidates = fetch_candidate_articles(n=10)
    for i, c in enumerate(candidates, 1):
        logger.info("      [%d] %s (%s)", i, c["title"], c["source"])

    logger.info("      Asking Ollama to pick the most TikTok-worthy article …")
    article = pick_best_article(candidates)
    logger.info("      Selected: %s (%s)", article["title"], article["source"])

    logger.info("      Fetching full text for selected article …")
    hydrate_article(article)  # fetches full_text, top_image, marks seen

    if topic:
        combined = (article["title"] + " " + article["summary"]).lower()
        if topic.lower() not in combined:
            raise NoNewArticlesError(
                f"Best article does not match topic filter '{topic}'."
            )

    # -----------------------------------------------------------------------
    # Step 2 – Generate script
    # -----------------------------------------------------------------------
    logger.info("[2/6] Generating TikTok script via %s …", llm_backend)
    script = generate_script(article, backend=llm_backend)
    word_count = len(script.split())
    logger.info("      Script: %d words.", word_count)

    # -----------------------------------------------------------------------
    # Step 3 – TTS voiceover
    # -----------------------------------------------------------------------
    audio_path = os.path.join(output_dir, "voiceover.wav")
    logger.info("[3/6] Synthesising voiceover with %s → %s …", tts_engine, audio_path)
    generate_voiceover(script, audio_path, engine=tts_engine)
    logger.info("      Voiceover written.")

    # -----------------------------------------------------------------------
    # Step 4 – Caption sync
    # -----------------------------------------------------------------------
    logger.info("[4/6] Extracting word timestamps …")
    words    = extract_word_timestamps(audio_path)
    captions = group_into_caption_chunks(words, chunk_size=config.CAPTION_CHUNK_SIZE)
    logger.info("      %d words → %d caption chunks.", len(words), len(captions))
    if not captions:
        raise CaptionSyncError("Whisper returned no words — voiceover may be silent or malformed.")

    # -----------------------------------------------------------------------
    # Step 5 – Fetch media inserts (article screenshot + stock images)
    # -----------------------------------------------------------------------
    logger.info("[5/7] Fetching media inserts (article image + stock photos) …")
    audio_duration = captions[-1]["end_time"] if captions else 30.0

    # Load the TTS timing sidecar so media queries match the script content
    timings_path = audio_path.replace(".wav", "_timings.json")
    tts_timings: list | None = None
    try:
        with open(timings_path) as _f:
            tts_timings = json.load(_f)
    except Exception as exc:
        logger.warning("Could not load TTS timings sidecar (%s) — media will be generic.", exc)

    media_inserts = fetch_media_inserts(
        article,
        audio_duration,
        output_dir,
        script=script,
        timings=tts_timings,
    )
    logger.info("      %d media insert(s) ready.", len(media_inserts))

    # -----------------------------------------------------------------------
    # Step 6 – Background
    # -----------------------------------------------------------------------
    logger.info("[6/7] Resolving background video …")
    bg_path  = get_background_video(audio_duration)
    logger.info("      Background: %s", bg_path)

    # -----------------------------------------------------------------------
    # Step 7 – Compose video
    # -----------------------------------------------------------------------
    output_path = os.path.join(output_dir, "output.mp4")
    logger.info("[7/7] Composing final video → %s …", output_path)
    compose_video(
        background_path=bg_path,
        audio_path=audio_path,
        captions=captions,
        output_path=output_path,
        resolution=config.VIDEO_RESOLUTION,
        media_inserts=media_inserts,
    )
    logger.info("      Done!  Output: %s", output_path)

    # Record the article in the human-readable video log CSV
    log_video_made(article, output_path)

    return output_path, article


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    args = _parse_args(argv)

    platforms = (
        [p.strip() for p in args.platforms.split(",")]
        if args.platforms else None
    )

    success = 0
    for i in range(args.batch):
        if args.batch > 1:
            logger.info("=== Batch run %d / %d ===", i + 1, args.batch)
        try:
            video_path, article = run_pipeline(
                topic=args.topic,
                tts_engine=args.tts_engine,
                llm_backend=args.llm_backend,
            )
            logger.info("Video ready: %s", video_path)
            if not args.no_upload:
                upload_to_all(video_path, article, platforms=platforms)
            success += 1
        except (NoNewArticlesError, ScriptGenerationError, TTSError,
                CaptionSyncError, VideoComposerError, BackgroundSourceError) as exc:
            logger.error("Pipeline failed: %s", exc)
        except Exception as exc:
            logger.exception("Unexpected error: %s", exc)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
