#!/usr/bin/env python3
"""
Summarizer for The AI Brief — sends collected content to Claude API
to generate a curated newsletter draft in markdown.

Usage:
    python3 summarizer.py                   # summarize today's collection
    python3 summarizer.py --date 2026-03-02
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta

from config import (
    CLAUDE_API_KEY, CLAUDE_MODEL, CLAUDE_MAX_TOKENS,
    COLLECTED_DIR, DRAFTS_DIR, NEWSLETTER_NAME,
)


SYSTEM_PROMPT = f"""You are the editor of "{NEWSLETTER_NAME}", a daily AI, tech, and startup newsletter for Oxford MBA students.

Write a sharp, concise, slightly witty digest. Your audience is smart, busy, and wants signal over noise. Cover AI, tech, startups, and venture capital.

Output markdown with EXACTLY these sections:

# {NEWSLETTER_NAME}

## Top AI Stories
5-7 items. Each item: **Bold headline** — 1-2 sentence summary. [Source](url)

## Funding & Deals
2-4 notable AI/tech startup funding rounds, acquisitions, or VC moves. Each: **Company — $Xm Series Y** — 1 sentence on what they do and why it matters. [Source](url)
If no funding news, skip this section entirely.

## Podcasts Worth Your Commute
3-5 recent episodes. Each: **Show — Episode title** — 1 sentence on why it's worth listening. [Listen](url)

## Events Near You
London/Oxford/Cambridge AI/tech/startup events this week. Each: **Event name** — date, location. [RSVP](url)
If no events found, write "Nothing on the radar this week — but keep an eye on lu.ma and Eventbrite."

## Videos Going Viral
3-5 notable AI/tech videos. Each: **Title** — 1 sentence summary. [Watch](url)

---

Rules:
- Be opinionated. Skip boring press releases. Highlight what actually matters.
- Keep each item to 1-2 sentences max. No filler.
- Use conversational tone but respect your audience's intelligence.
- If the source data is thin, say so briefly rather than padding.
- End with a one-liner sign-off like "Stay curious." or similar."""


def build_prompt(items, target_date):
    """Build the user prompt from collected items."""
    # Parse the date for day-of-week
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        day_name = dt.strftime("%A")
        date_display = dt.strftime("%B %d, %Y")
    except ValueError:
        day_name = ""
        date_display = target_date

    # Group items by type
    articles = [i for i in items if i.get("type") == "article"]
    podcasts = [i for i in items if i.get("type") == "podcast"]
    events = [i for i in items if i.get("type") == "event"]
    videos = [i for i in items if i.get("type") == "video"]

    prompt_parts = [
        f"Today is {day_name}, {date_display}.",
        f"Write today's issue of {NEWSLETTER_NAME}.",
        "",
    ]

    if articles:
        prompt_parts.append(f"=== ARTICLES ({len(articles)} items) ===")
        for a in articles:
            prompt_parts.append(f"- [{a['source']}] {a['title']}")
            if a.get("summary"):
                prompt_parts.append(f"  Summary: {a['summary'][:200]}")
            if a.get("url"):
                prompt_parts.append(f"  URL: {a['url']}")
            prompt_parts.append("")

    if podcasts:
        prompt_parts.append(f"=== PODCASTS ({len(podcasts)} items) ===")
        for p in podcasts:
            prompt_parts.append(f"- [{p['source']}] {p['title']}")
            if p.get("url"):
                prompt_parts.append(f"  URL: {p['url']}")
            prompt_parts.append("")

    if events:
        prompt_parts.append(f"=== EVENTS ({len(events)} items) ===")
        for e in events:
            prompt_parts.append(f"- [{e['source']}] {e['title']}")
            if e.get("url"):
                prompt_parts.append(f"  URL: {e['url']}")
            prompt_parts.append("")

    if videos:
        prompt_parts.append(f"=== VIDEOS ({len(videos)} items) ===")
        for v in videos:
            prompt_parts.append(f"- [{v['source']}] {v['title']}")
            if v.get("url"):
                prompt_parts.append(f"  URL: {v['url']}")
            prompt_parts.append("")

    if not items:
        prompt_parts.append("No content was collected today. Write a brief note acknowledging this.")

    return "\n".join(prompt_parts)


def call_claude(system_prompt, user_prompt):
    """Call Claude API via direct HTTP (no SDK). Returns response text."""
    if not CLAUDE_API_KEY:
        print("  [ERROR] CLAUDE_API_KEY not set in .env")
        sys.exit(1)

    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": CLAUDE_MAX_TOKENS,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  [ERROR] Claude API HTTP {e.code}: {body[:500]}")
        sys.exit(1)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"  [ERROR] Claude API request failed: {e}")
        sys.exit(1)

    # Extract text from response
    content = data.get("content", [])
    text_parts = [block["text"] for block in content if block.get("type") == "text"]
    return "\n".join(text_parts)


def build_local_draft(items, target_date):
    """Build a newsletter draft locally from collected data (no API needed).
    Groups items by type, picks the top ones, and formats as markdown."""
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        date_display = dt.strftime("%A, %B %d, %Y")
    except ValueError:
        date_display = target_date

    articles = [i for i in items if i.get("type") == "article"]
    podcasts = sorted(
        [i for i in items if i.get("type") == "podcast"],
        key=lambda x: x.get("date", ""), reverse=True,
    )
    events = [i for i in items if i.get("type") == "event"]
    videos = sorted(
        [i for i in items if i.get("type") == "video"],
        key=lambda x: x.get("date", ""), reverse=True,
    )

    # Separate funding/VC articles from general articles
    funding_keywords = ["funding", "raise", "series", "valuation", "venture",
                        "invest", "round", "million", "billion", "acquisition",
                        "acquire", "ipo", "fundrais", "seed", "capital"]
    funding_articles = []
    general_articles = []
    for a in articles:
        text = (a.get("title", "") + " " + a.get("summary", "")).lower()
        if any(kw in text for kw in funding_keywords):
            funding_articles.append(a)
        else:
            general_articles.append(a)

    lines = [f"# {NEWSLETTER_NAME}", f"*{date_display}*", ""]

    # Top AI Stories — pick up to 7
    lines.append("## Top AI Stories")
    lines.append("")
    for a in general_articles[:7]:
        title = a["title"].strip()
        summary = (a.get("summary") or "").strip()
        url = a.get("url", "")
        source = a.get("source", "")
        # Truncate summary to first sentence
        if summary:
            first_sentence = summary.split(". ")[0].rstrip(".")
            if len(first_sentence) > 150:
                first_sentence = first_sentence[:147] + "..."
            lines.append(f"- **{title}** — {first_sentence}. [{source}]({url})")
        else:
            lines.append(f"- **{title}** [{source}]({url})")
        lines.append("")
    if not general_articles:
        lines.append("Quiet day on the feeds. Check back tomorrow.")
        lines.append("")

    # Funding & Deals
    if funding_articles:
        lines.append("## Funding & Deals")
        lines.append("")
        for a in funding_articles[:4]:
            title = a["title"].strip()
            summary = (a.get("summary") or "").strip()
            url = a.get("url", "")
            source = a.get("source", "")
            if summary:
                first_sentence = summary.split(". ")[0].rstrip(".")
                if len(first_sentence) > 150:
                    first_sentence = first_sentence[:147] + "..."
                lines.append(f"- **{title}** — {first_sentence}. [{source}]({url})")
            else:
                lines.append(f"- **{title}** [{source}]({url})")
            lines.append("")

    # Podcasts
    lines.append("## Podcasts Worth Your Commute")
    lines.append("")
    if podcasts:
        for p in podcasts[:5]:
            title = p["title"].strip()
            url = p.get("url", "")
            source = p.get("source", "")
            lines.append(f"- **{source} — {title}** [Listen]({url})")
            lines.append("")
    else:
        lines.append("Podcast feeds are quiet today — check back tomorrow for fresh episodes.")
        lines.append("")

    # Events
    lines.append("## Events Near You (London & Oxford)")
    lines.append("")
    if events:
        for e in events[:8]:
            title = e["title"].strip()
            url = e.get("url", "")
            source = e.get("source", "")
            lines.append(f"- **{title}** — {source}. [RSVP]({url})")
            lines.append("")
    else:
        lines.append("Nothing on the radar this week — browse lu.ma and Eventbrite for last-minute additions.")
        lines.append("")

    # Videos
    lines.append("## Videos Going Viral")
    lines.append("")
    if videos:
        for v in videos[:5]:
            title = v["title"].strip()
            url = v.get("url", "")
            source = v.get("source", "")
            lines.append(f"- **{title}** — {source}. [Watch]({url})")
            lines.append("")
    else:
        lines.append("No standout videos today — the creators are probably busy recording.")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("Stay curious.")
    lines.append("")

    return "\n".join(lines)


def load_recent_items_by_type(target_date, item_type, lookback_days=7):
    """Load items of a given type from recent collected JSON files.

    The collector deduplicates by URL across runs, so podcasts and videos
    that were fetched on previous days may not appear in today's collected
    file.  This function scans the last ``lookback_days`` collected files
    (including today's) and returns all items matching ``item_type``,
    deduplicated by URL with the most recent occurrence kept.
    """
    try:
        base = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        base = date.today()

    seen_urls = set()
    items = []

    # Walk backwards from target_date so newer items take priority
    for offset in range(lookback_days):
        day = base - timedelta(days=offset)
        path = COLLECTED_DIR / f"{day.isoformat()}.json"
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                day_items = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        for item in day_items:
            if item.get("type") != item_type:
                continue
            url = item.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            items.append(item)

    return items


def summarize(target_date=None, local_mode=False):
    """Load collected data, generate draft (via Claude or locally), save it."""
    if target_date is None:
        target_date = date.today().isoformat()

    collected_file = COLLECTED_DIR / f"{target_date}.json"
    if not collected_file.exists():
        print(f"  [ERROR] No collected data for {target_date}")
        print(f"  Run: python3 collector.py --date {target_date}")
        sys.exit(1)

    with open(collected_file, "r", encoding="utf-8") as f:
        items = json.load(f)

    # The collector deduplicates all items by URL using seen_articles.json,
    # which means podcasts and videos fetched on earlier days won't appear
    # in today's collected file even though their episodes are still recent.
    # Supplement today's items with podcast/video data from recent days.
    today_podcasts = [i for i in items if i.get("type") == "podcast"]
    today_videos = [i for i in items if i.get("type") == "video"]

    if len(today_podcasts) < 3:
        recent_podcasts = load_recent_items_by_type(target_date, "podcast")
        # Merge: keep today's items, add recent ones that aren't duplicates
        existing_urls = {i.get("url") for i in items if i.get("type") == "podcast"}
        for p in recent_podcasts:
            if p.get("url") not in existing_urls:
                items.append(p)
                existing_urls.add(p.get("url"))
        added_podcasts = len([i for i in items if i.get("type") == "podcast"]) - len(today_podcasts)
        if added_podcasts > 0:
            print(f"  Supplemented with {added_podcasts} podcast(s) from recent days")

    if len(today_videos) < 3:
        recent_videos = load_recent_items_by_type(target_date, "video")
        existing_urls = {i.get("url") for i in items if i.get("type") == "video"}
        for v in recent_videos:
            if v.get("url") not in existing_urls:
                items.append(v)
                existing_urls.add(v.get("url"))
        added_videos = len([i for i in items if i.get("type") == "video"]) - len(today_videos)
        if added_videos > 0:
            print(f"  Supplemented with {added_videos} video(s) from recent days")

    print(f"\nThe AI Brief — Summarizer — {target_date}")
    print("=" * 50)
    print(f"  Loaded {len(items)} items from {collected_file.name}")

    if local_mode or not CLAUDE_API_KEY:
        if not CLAUDE_API_KEY and not local_mode:
            print("  [INFO] No CLAUDE_API_KEY set — using local template mode")
        else:
            print("  Using local template mode (--local)")
        draft = build_local_draft(items, target_date)
    else:
        user_prompt = build_prompt(items, target_date)
        print(f"  Calling Claude ({CLAUDE_MODEL})...")
        draft = call_claude(SYSTEM_PROMPT, user_prompt)

    # Save draft
    draft_file = DRAFTS_DIR / f"{target_date}.md"
    with open(draft_file, "w", encoding="utf-8") as f:
        f.write(draft)

    print(f"  Draft saved to {draft_file}")
    print(f"\n  Review and edit the draft, then run:")
    print(f"    python3 publisher.py --date {target_date}")

    return draft_file


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    target_date = None
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            target_date = sys.argv[idx + 1]

    local_mode = "--local" in sys.argv
    summarize(target_date, local_mode=local_mode)


if __name__ == "__main__":
    main()
