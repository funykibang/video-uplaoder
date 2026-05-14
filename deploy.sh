#!/usr/bin/env bash
# deploy.sh — one-shot setup for Oracle Cloud (Ubuntu 22.04, ARM64 Ampere A1).
#
# Usage — from your local machine:
#   scp -r . ubuntu@<server-ip>:/tmp/video-uploader
#   ssh ubuntu@<server-ip> "cd /tmp/video-uploader && bash deploy.sh"
#
# The script uses sudo internally — run as the default 'ubuntu' user, not root.
set -euo pipefail

APP_DIR=/opt/video-uploader
VENV=$APP_DIR/venv
SERVICE_USER=videobot

echo "=== [1/6] Installing system packages ==="
sudo apt-get update -y
# python3.11-venv, ffmpeg, and git are all available in Ubuntu 22.04 ARM64 repos
sudo apt-get install -y python3.11 python3.11-venv python3-pip ffmpeg git rsync

echo "=== [2/6] Creating service user '$SERVICE_USER' ==="
id $SERVICE_USER &>/dev/null || sudo useradd -r -m -s /bin/bash $SERVICE_USER

echo "=== [3/6] Copying app files to $APP_DIR ==="
sudo mkdir -p $APP_DIR
sudo rsync -a --delete \
  --exclude='.env' \
  --exclude='output/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache/' \
  --exclude='.ruff_cache/' \
  --exclude='dedup.db' \
  --exclude='instagram_session.json' \
  --exclude='videos_log.csv' \
  "$(dirname "$0")/" $APP_DIR/
sudo chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR

echo "=== [4/6] Creating Python virtual environment ==="
sudo -u $SERVICE_USER python3.11 -m venv $VENV
sudo -u $SERVICE_USER $VENV/bin/pip install --upgrade pip --quiet
# faster-whisper and CTranslate2 have official ARM64 wheels on PyPI — no special flags needed
sudo -u $SERVICE_USER $VENV/bin/pip install -r $APP_DIR/requirements.txt --quiet
echo "    Dependencies installed."

echo "=== [5/6] Setting up .env ==="
if [ ! -f $APP_DIR/.env ]; then
  sudo cp $APP_DIR/.env.example $APP_DIR/.env
  echo "    Copied .env.example → .env  — EDIT IT before starting the service!"
else
  echo "    .env already exists, skipping."
fi
sudo chmod 600 $APP_DIR/.env
sudo chown $SERVICE_USER:$SERVICE_USER $APP_DIR/.env

echo "=== [6/6] Installing and starting systemd service ==="
sudo cp $APP_DIR/video-uploader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable video-uploader
sudo systemctl restart video-uploader

echo ""
echo "=== Done! ==="
sudo systemctl status video-uploader --no-pager -l
echo ""
echo "Useful commands:"
echo "  sudo journalctl -u video-uploader -f        # live logs"
echo "  sudo systemctl restart video-uploader       # restart"
echo "  sudo nano $APP_DIR/.env                     # edit config"
echo ""
echo "Don't forget to copy your background video:"
echo "  scp background.mp4 ubuntu@<ip>:/tmp/"
echo "  sudo mv /tmp/background.mp4 $APP_DIR/assets/backgrounds/"
echo "  sudo chown $SERVICE_USER:$SERVICE_USER $APP_DIR/assets/backgrounds/background.mp4"
