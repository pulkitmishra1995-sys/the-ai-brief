#!/bin/bash
# The AI Brief — daily collection + summarization wrapper
# Called by launchd at 7 AM weekdays

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/newsletter.log"

# Log rotation: if > 1MB, keep one backup
if [ -f "$LOG" ]; then
    size=$(stat -f%z "$LOG" 2>/dev/null || stat -c%s "$LOG" 2>/dev/null || echo 0)
    if [ "$size" -gt 1048576 ]; then
        mv "$LOG" "$LOG.old"
    fi
fi

echo "========================================" >> "$LOG"
echo "$(date '+%Y-%m-%d %H:%M:%S') — Starting" >> "$LOG"

# Source environment
if [ -f "$DIR/.env" ]; then
    set -a
    source "$DIR/.env"
    set +a
fi

cd "$DIR"

# Step 1: Collect content
echo "$(date '+%H:%M:%S') Collecting..." >> "$LOG"
/usr/bin/python3 collector.py >> "$LOG" 2>&1

# Step 2: Generate draft via Claude
echo "$(date '+%H:%M:%S') Summarizing..." >> "$LOG"
/usr/bin/python3 summarizer.py >> "$LOG" 2>&1

echo "$(date '+%H:%M:%S') Done. Review draft in drafts/" >> "$LOG"
echo "========================================" >> "$LOG"
