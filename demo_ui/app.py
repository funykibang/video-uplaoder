"""
demo_ui/app.py
~~~~~~~~~~~~~~
Simple web UI for scheduling / uploading videos to TikTok.
Used as the demo app for TikTok's Content Posting API review.

Usage
-----
python demo_ui/app.py
then open http://localhost:5000
"""

import os
import sys
import threading
import uuid
import logging
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_from_directory

# Add project root to path so we can import the pipeline
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.uploader.tiktok import upload_to_tiktok

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo_ui")

# In-memory job store: job_id -> {"status", "message", "publish_id", "scheduled_at"}
_jobs: dict = {}


def _do_upload(job_id: str, video_path: str, title: str, caption: str) -> None:
    """Background thread: upload to TikTok and update job status."""
    _jobs[job_id]["status"] = "uploading"
    try:
        publish_id = upload_to_tiktok(video_path, title, caption)
        _jobs[job_id].update(status="done", publish_id=publish_id,
                             message="Uploaded successfully!")
    except Exception as exc:
        logger.error("Upload failed: %s", exc)
        _jobs[job_id].update(status="error", message=str(exc))
    finally:
        try:
            os.remove(video_path)
        except OSError:
            pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """Upload now (immediately)."""
    video = request.files.get("video")
    title   = request.form.get("title", "").strip() or "Tech News"
    caption = request.form.get("caption", "").strip()

    if not video or not video.filename:
        return jsonify(error="No video file provided."), 400

    ext      = os.path.splitext(video.filename)[-1].lower() or ".mp4"
    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    video.save(save_path)

    job_id = uuid.uuid4().hex
    _jobs[job_id] = {
        "status":       "queued",
        "message":      "Upload queued…",
        "publish_id":   None,
        "scheduled_at": None,
        "title":        title,
        "created_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    t = threading.Thread(target=_do_upload, args=(job_id, save_path, title, caption), daemon=True)
    t.start()

    return jsonify(job_id=job_id)


@app.route("/schedule", methods=["POST"])
def schedule_post():
    """Schedule a future upload (stores the job and fires at the right time)."""
    video      = request.files.get("video")
    title      = request.form.get("title", "").strip() or "Tech News"
    caption    = request.form.get("caption", "").strip()
    scheduled_at = request.form.get("scheduled_at", "").strip()

    if not video or not video.filename:
        return jsonify(error="No video file provided."), 400
    if not scheduled_at:
        return jsonify(error="No schedule time provided."), 400

    try:
        fire_dt = datetime.fromisoformat(scheduled_at)
    except ValueError:
        return jsonify(error="Invalid date/time format."), 400

    ext      = os.path.splitext(video.filename)[-1].lower() or ".mp4"
    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    video.save(save_path)

    job_id = uuid.uuid4().hex
    _jobs[job_id] = {
        "status":       "scheduled",
        "message":      f"Scheduled for {fire_dt.strftime('%Y-%m-%d %H:%M')}",
        "publish_id":   None,
        "scheduled_at": fire_dt.strftime("%Y-%m-%d %H:%M"),
        "title":        title,
        "created_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    delay = max(0, (fire_dt - datetime.now()).total_seconds())

    def _fire():
        import time
        time.sleep(delay)
        _do_upload(job_id, save_path, title, caption)

    threading.Thread(target=_fire, daemon=True).start()

    return jsonify(job_id=job_id, scheduled_at=fire_dt.strftime("%Y-%m-%d %H:%M"))


@app.route("/status/<job_id>")
def status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return jsonify(error="Unknown job."), 404
    return jsonify(job)


@app.route("/jobs")
def jobs():
    return jsonify(list(_jobs.items()))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
