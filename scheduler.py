"""
scheduler.py
~~~~~~~~~~~~
Long-running process that fires the full pipeline (generate + upload)
3× per day at times configured in SCHEDULE_TIMES.

Usage
-----
python scheduler.py

The process blocks forever — run it under systemd, supervisord, screen,
or tmux on the server.  All times are in the server's local timezone.
"""

import logging
import os
import shutil
import time

import schedule

import config
from main import run_pipeline
from pipeline.uploader import upload_to_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")


def _cleanup_output() -> None:
    """Delete all files inside OUTPUT_DIR to free disk space."""
    output_dir = config.OUTPUT_DIR
    if not os.path.isdir(output_dir):
        logger.info("Cleanup: output dir does not exist, nothing to do.")
        return

    total_bytes = 0
    deleted = 0
    for name in os.listdir(output_dir):
        path = os.path.join(output_dir, name)
        try:
            size = os.path.getsize(path)
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
            total_bytes += size
            deleted += 1
        except Exception as exc:
            logger.warning("Could not delete %s: %s", path, exc)

    mb = total_bytes / (1024 * 1024)
    logger.info("Cleanup: removed %d item(s), freed %.1f MB from %s", deleted, mb, output_dir)


def _run_job() -> None:
    logger.info("=== Scheduled pipeline run starting ===")
    try:
        video_path, article = run_pipeline(llm_backend="claude")
        logger.info("Video ready: %s", video_path)
        upload_to_all(video_path, article)
    except Exception as exc:
        logger.exception("Scheduled run failed: %s", exc)
    logger.info("=== Scheduled run complete ===")


def main() -> None:
    for t in config.SCHEDULE_TIMES:
        schedule.every().day.at(t).do(_run_job)
        logger.info("Scheduled daily run at %s (server local time)", t)

    schedule.every().day.at(config.CLEANUP_TIME).do(_cleanup_output)
    logger.info("Scheduled daily cleanup at %s (server local time)", config.CLEANUP_TIME)

    logger.info("Scheduler running. Waiting for next job...")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
