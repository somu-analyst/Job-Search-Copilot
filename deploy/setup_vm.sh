#!/usr/bin/env bash
# deploy/setup_vm.sh -- idempotent bootstrap for the Oracle VM (nyse-bot @ 150.136.41.250).
# Deliberately its own directory/venv/systemd units, separate from /home/ubuntu/nyse --
# this project has nothing to do with the trading bot, it just shares the free-tier box.
#
# Run ON the VM (as ubuntu):
#   bash setup_vm.sh
#
# What it does NOT do: place your real config/profile.yml, resume/cv.md, or OpenRouter key.
# Those are your secrets -- see deploy/README.md for the one-time scp step. Safe to re-run
# before that step: the app falls back to its committed demo data, same as a fresh clone.
set -euo pipefail

REPO_URL="https://github.com/somu-analyst/Job-Search-Copilot.git"
APP_DIR="/home/ubuntu/job-search-copilot"

if [ -d "$APP_DIR/.git" ]; then
    echo "Repo exists -- pulling latest"
    git -C "$APP_DIR" pull --ff-only
else
    echo "Cloning $REPO_URL"
    git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt

echo "Installing systemd units"
sudo cp deploy/jobscout-scan.service deploy/jobscout-scan.timer deploy/jobscout-dashboard.service \
    /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jobscout-scan.timer
sudo systemctl enable --now jobscout-dashboard.service

echo
echo "Done. Status:"
systemctl status jobscout-scan.timer jobscout-dashboard.service --no-pager | grep -E "Loaded|Active"
echo
echo "The dashboard is running on demo data until you scp your real config -- see deploy/README.md."
echo "View it now:  ssh -i ~/oci-nyse.key -L 8503:127.0.0.1:8503 ubuntu@150.136.41.250"
