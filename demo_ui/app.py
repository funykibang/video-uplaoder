"""
demo_ui/app.py
~~~~~~~~~~~~~~
Demo web UI for scheduling / uploading videos to TikTok.

Runs in two modes:
  - DEMO MODE  (default, no TikTok credentials needed)
    Upload/schedule endpoints return immediately; status is simulated
    via time-encoded job IDs so polling works even across serverless
    instances (Vercel).
  - LIVE MODE  (TIKTOK_ACCESS_TOKEN set in env)
    Actually calls the TikTok Content Posting API.

Usage (local)
-------------
python demo_ui/app.py          → http://localhost:5000

Usage (Vercel)
--------------
vercel deploy  (from repo root)
"""

import logging
import os
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime

from flask import Flask, jsonify, render_template, request

logger = logging.getLogger("demo_ui")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__, template_folder="templates")
app.config["UPLOAD_FOLDER"] = os.path.join(tempfile.gettempdir(), "tiktok_demo_uploads")
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Live mode only when real credentials are present
_LIVE_MODE = bool(os.environ.get("TIKTOK_ACCESS_TOKEN"))

# ---------------------------------------------------------------------------
# Job ID encodes creation time so status works across serverless instances.
# Format: "{unix_ms}_{8-char-hex}"
# ---------------------------------------------------------------------------

def _new_job_id() -> str:
    return f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


def _job_age(job_id: str) -> float:
    """Seconds since job was created, derived from the job_id itself."""
    try:
        return time.time() - int(job_id.split("_")[0]) / 1000
    except Exception:
        return 9999


def _demo_status(job_id: str) -> dict:
    """Simulate upload progress based purely on elapsed time."""
    age = _job_age(job_id)
    token = job_id.split("_")[-1]
    if age < 1.2:
        return {"status": "queued",    "message": "Upload queued…",         "publish_id": None}
    if age < 5.0:
        return {"status": "uploading", "message": "Uploading to TikTok…",   "publish_id": None}
    return      {"status": "done",     "message": "Uploaded successfully!",  "publish_id": f"demo_{token}"}


# In-process store for live mode (same instance handles the thread + poll)
_live_jobs: dict = {}


def _do_live_upload(job_id: str, video_path: str, title: str, caption: str) -> None:
    _live_jobs[job_id] = {"status": "uploading", "message": "Uploading to TikTok…", "publish_id": None}
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from pipeline.uploader.tiktok import upload_to_tiktok  # imported lazily
        publish_id = upload_to_tiktok(video_path, title, caption)
        _live_jobs[job_id].update(status="done", message="Uploaded successfully!", publish_id=publish_id)
    except Exception as exc:
        logger.error("TikTok upload error: %s", exc)
        _live_jobs[job_id].update(status="error", message=str(exc))
    finally:
        try:
            os.remove(video_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/upload", methods=["POST"])
def upload():
    video   = request.files.get("video")
    title   = request.form.get("title",   "").strip() or "Tech News"
    caption = request.form.get("caption", "").strip()

    if not video or not video.filename:
        return jsonify(error="No video file provided."), 400

    job_id = _new_job_id()

    if _LIVE_MODE:
        ext       = os.path.splitext(video.filename)[-1].lower() or ".mp4"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{job_id}{ext}")
        video.save(save_path)
        _live_jobs[job_id] = {"status": "queued", "message": "Upload queued…", "publish_id": None}
        threading.Thread(target=_do_live_upload,
                         args=(job_id, save_path, title, caption), daemon=True).start()
    # demo mode: just discard the bytes, status is time-based

    return jsonify(job_id=job_id)


@app.route("/schedule", methods=["POST"])
def schedule_post():
    video        = request.files.get("video")
    title        = request.form.get("title",        "").strip() or "Tech News"
    caption      = request.form.get("caption",      "").strip()
    scheduled_at = request.form.get("scheduled_at", "").strip()

    if not video or not video.filename:
        return jsonify(error="No video file provided."), 400
    if not scheduled_at:
        return jsonify(error="No schedule time provided."), 400

    try:
        fire_dt = datetime.fromisoformat(scheduled_at)
    except ValueError:
        return jsonify(error="Invalid date/time format."), 400

    job_id = _new_job_id()

    if _LIVE_MODE:
        ext       = os.path.splitext(video.filename)[-1].lower() or ".mp4"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{job_id}{ext}")
        video.save(save_path)
        _live_jobs[job_id] = {
            "status": "scheduled",
            "message": f"Scheduled for {fire_dt.strftime('%Y-%m-%d %H:%M')}",
            "publish_id": None,
            "scheduled_at": fire_dt.strftime("%Y-%m-%d %H:%M"),
        }
        delay = max(0, (fire_dt - datetime.now()).total_seconds())
        def _fire():
            time.sleep(delay)
            _do_live_upload(job_id, save_path, title, caption)
        threading.Thread(target=_fire, daemon=True).start()

    return jsonify(
        job_id=job_id,
        scheduled_at=fire_dt.strftime("%Y-%m-%d %H:%M"),
    )


@app.route("/status/<job_id>")
def status(job_id: str):
    if _LIVE_MODE and job_id in _live_jobs:
        return jsonify(_live_jobs[job_id])
    return jsonify(_demo_status(job_id))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
