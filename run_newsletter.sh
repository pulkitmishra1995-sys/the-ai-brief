#!/bin/bash
# The AI Brief — daily collection + summarization wrapper
# Called by launchd at 7 AM weekdays

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/newsletter.log"

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
