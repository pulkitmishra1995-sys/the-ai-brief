#!/usr/bin/env python3
"""
Health check CLI for Oxford AI Pulse — feed status and link checker.

Usage:
    python3 healthcheck.py --feeds          # check all feed URLs
    python3 healthcheck.py --links [date]   # check external URLs in a published issue
    python3 healthcheck.py --all            # run both
"""

import re
import sys
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

from config import (
    RSS_FEEDS, PODCAST_FEEDS, YOUTUBE_CHANNELS,
    ISSUES_DIR, USER_AGENT, FEED_HEALTH_FILE,
)


def check_url(url, timeout=10):
    """Send a HEAD request to url. Returns (status_code, error_string)."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, None
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, str(e)


def check_feeds():
    """Check all configured feed URLs and print a report."""
    print("\n=== Feed Health Check ===\n")
    all_feeds = {}
    for name, info in RSS_FEEDS.items():
        all_feeds[info["url"]] = name
    for name, info in PODCAST_FEEDS.items():
        all_feeds[info["url"]] = name
    for name, info in YOUTUBE_CHANNELS.items():
        all_feeds[info["url"]] = name

    ok_count = 0
    fail_count = 0

    for url, name in sorted(all_feeds.items(), key=lambda x: x[1]):
        status, error = check_url(url)
        if status and 200 <= status < 400:
            print(f"  [OK {status}] {name}: {url}")
            ok_count += 1
        elif status:
            print(f"  [FAIL {status}] {name}: {url}")
            fail_count += 1
        else:
            print(f"  [TIMEOUT] {name}: {url} — {error}")
            fail_count += 1

    print(f"\n  Results: {ok_count} OK, {fail_count} failed out of {ok_count + fail_count} feeds\n")
    return fail_count == 0


def check_links(target_date=None):
    """Check all external URLs in a published issue HTML for broken links."""
    if target_date is None:
        target_date = date.today().isoformat()

    issue_file = ISSUES_DIR / f"{target_date}.html"
    if not issue_file.exists():
        print(f"  No issue found at {issue_file}")
        return False

    print(f"\n=== Link Check for {target_date} ===\n")

    with open(issue_file, "r", encoding="utf-8") as f:
        html = f.read()

    # Extract all href URLs
    urls = set(re.findall(r'href="(https?://[^"]+)"', html))
    print(f"  Found {len(urls)} unique external URLs\n")

    ok_count = 0
    fail_count = 0

    for url in sorted(urls):
        status, error = check_url(url)
        if status and 200 <= status < 400:
            print(f"  [OK {status}] {url}")
            ok_count += 1
        elif status:
            print(f"  [FAIL {status}] {url}")
            fail_count += 1
        else:
            print(f"  [TIMEOUT] {url} — {error}")
            fail_count += 1

    print(f"\n  Results: {ok_count} OK, {fail_count} failed out of {ok_count + fail_count} links\n")
    return fail_count == 0


def main():
    if len(sys.argv) < 2 or "--help" in sys.argv:
        print(__doc__)
        sys.exit(0)

    run_feeds = "--feeds" in sys.argv or "--all" in sys.argv
    run_links = "--links" in sys.argv or "--all" in sys.argv

    if not run_feeds and not run_links:
        print("Error: specify --feeds, --links [date], or --all")
        sys.exit(1)

    # Parse optional date argument for --links
    target_date = None
    if "--links" in sys.argv:
        idx = sys.argv.index("--links")
        if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("-"):
            target_date = sys.argv[idx + 1]

    all_ok = True
    if run_feeds:
        if not check_feeds():
            all_ok = False
    if run_links:
        if not check_links(target_date):
            all_ok = False

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
