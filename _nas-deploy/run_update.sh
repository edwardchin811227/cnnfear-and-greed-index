#!/bin/bash
set -e

export HTTPS_PROXY="${HTTPS_PROXY:-http://192.168.31.237:7890}"
export HTTP_PROXY="${HTTP_PROXY:-http://192.168.31.237:7890}"
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,.local}"

REPO_DIR="/app/cnnfear-and-greed-index"
LOG_DIR="/app/logs"
LOG_FILE="$LOG_DIR/daily_update.log"

mkdir -p "$LOG_DIR"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S')  $1" | tee -a "$LOG_FILE"
}

log "=== Daily update start ==="

if [ ! -d "$REPO_DIR/.git" ]; then
    log "ERROR: Repository directory $REPO_DIR does not exist."
    exit 1
fi

cd "$REPO_DIR"

log "Pulling latest changes..."
git pull --rebase origin main >> "$LOG_FILE" 2>&1

log "Running fetch script..."
python scripts/fetch_and_process.py --backfill-days 10 >> "$LOG_FILE" 2>&1

log "Checking for changes..."
git add data/fng.csv docs/fng_data.json
if git diff --cached --quiet; then
    log "No data change. Skip commit/push."
else
    log "Changes detected, committing and pushing..."
    git commit -m "data: update fng $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE" 2>&1
    git push origin main >> "$LOG_FILE" 2>&1
    log "Commit + push completed."
fi

log "=== Daily update end ==="
echo "" >> "$LOG_FILE"
