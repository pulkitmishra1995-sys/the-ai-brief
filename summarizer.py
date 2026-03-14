#!/usr/bin/env python3
"""
Summarizer for Oxford AI Pulse — sends collected content to Claude API
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


SYSTEM_PROMPT = f"""You are the editor of "{NEWSLETTER_NAME}", a daily AI, tech, and startup newsletter for Oxford MBA students and the broader Oxford community.

Write a sharp, insightful, slightly witty digest. Your audience is smart, ambitious, and wants signal over noise. They care about AI, tech, startups, venture capital, and how these trends reshape business and society.

Output markdown with EXACTLY these sections:

# {NEWSLETTER_NAME}

## Top AI Stories
5-7 items. For each item:
- **Bold headline** — 2-3 sentence summary covering what happened and key details (funding amounts, user numbers, technical specs where relevant).
- **Why it matters:** 1 sentence on the broader significance — what does this mean for the industry, for builders, or for business leaders?
- [Source](url)

## Funding & Deals
2-4 notable AI/tech startup funding rounds, acquisitions, or VC moves. For each:
- **Company — $Xm Series Y** — 2 sentences: what the company does and what the funding signals about the market.
- **Why it matters:** 1 sentence on the investment thesis or market trend.
- [Source](url)
If no funding news, skip this section entirely.

## Podcasts Worth Your Commute
3-5 recent episodes. Each: **Show — Episode title** — 1-2 sentences on the key takeaway and why it's worth listening. [Listen](url)

## Events Near You
London/Oxford/Cambridge AI/tech/startup events this week. Each: **Event name** — date, location. [RSVP](url)
If no events found, write "Nothing on the radar this week — but keep an eye on lu.ma and Eventbrite."

## Videos Going Viral
3-5 notable AI/tech videos. Each: **Title** — 1-2 sentence summary of the key insight. [Watch](url)

---

Formatting rules (CRITICAL — follow these exactly):
- **Bold ALL metrics** in summaries: dollar amounts (**$50M**, **$1.2B**), percentages (**76.8%**, **2.5%**), multipliers (**2.5x faster**), benchmarks (**1432 Elo**), token counts (**128K tokens**), user numbers (**1.5 billion users**).
- **Bold company and model names** on first mention in each item: **OpenAI**, **Claude Opus**, **Gemini Flash**, **Meta**, etc.
- "Why it matters" must connect the news to a broader trend — market shifts, competitive dynamics, regulatory impact, or career implications for builders and business leaders.
- Be opinionated. Skip boring press releases. Highlight what actually matters.
- Pull key quotes from articles when they're punchy and illuminating.
- Use conversational tone but respect your audience's intelligence — these are MBAs and founders.
- If the source data is thin, say so briefly rather than padding.
- End with a one-liner sign-off like "Stay curious." or similar.

Here is a concrete example of one well-formatted item:

- **OpenAI Launches GPT-5 with Native Tool Use** — **OpenAI** released **GPT-5** today, featuring native tool use and a **128K token** context window. Early benchmarks show **92.1%** on MMLU and **1432 Elo** on Chatbot Arena, a **2.5x** improvement in reasoning tasks over GPT-4o. API pricing starts at **$0.25/M** input tokens. [TechCrunch](url)
  - **Why it matters:** This closes the gap with Claude and Gemini on agentic tasks — expect every AI startup to re-benchmark this week."""


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
                prompt_parts.append(f"  Summary: {a['summary'][:500]}")
            if a.get("url"):
                prompt_parts.append(f"  URL: {a['url']}")
            prompt_parts.append("")

    if podcasts:
        prompt_parts.append(f"=== PODCASTS ({len(podcasts)} items) ===")
        for p in podcasts:
            prompt_parts.append(f"- [{p['source']}] {p['title']}")
            if p.get("summary"):
                prompt_parts.append(f"  Summary: {p['summary'][:300]}")
            if p.get("url"):
                prompt_parts.append(f"  URL: {p['url']}")
            prompt_parts.append("")

    if events:
        prompt_parts.append(f"=== EVENTS ({len(events)} items) ===")
        for e in events:
            prompt_parts.append(f"- [{e['source']}] {e['title']}")
            if e.get("date"):
                prompt_parts.append(f"  Date: {e['date']}")
            if e.get("url"):
                prompt_parts.append(f"  URL: {e['url']}")
            prompt_parts.append("")

    if videos:
        prompt_parts.append(f"=== VIDEOS ({len(videos)} items) ===")
        for v in videos:
            prompt_parts.append(f"- [{v['source']}] {v['title']}")
            if v.get("summary"):
                prompt_parts.append(f"  Summary: {v['summary'][:300]}")
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


def _bold_metrics_in_markdown(text):
    """Bold metrics in markdown text using **X** syntax."""
    import re as _re
    # Dollar amounts: $50M, $1.2B, $500K, $2.5 billion, $100 million
    text = _re.sub(
        r'(\$[\d,.]+\s*(?:[BMKbmk]|billion|million|thousand)\b)',
        r'**\1**', text
    )
    # Percentages: 76.8%, 2.5%
    text = _re.sub(r'([\d,.]+%)', r'**\1**', text)
    # Multipliers: 2.5x faster, 10x
    text = _re.sub(
        r'([\d,.]+x(?:\s+(?:faster|slower|cheaper|more|less|improvement|better|larger|smaller))?)',
        r'**\1**', text, flags=_re.IGNORECASE
    )
    # Elo scores: 1432 Elo
    text = _re.sub(r'([\d,]+\s+Elo)', r'**\1**', text)
    # Token counts: 128K tokens, 1M tokens
    text = _re.sub(
        r'([\d,.]+[KMBkmb]\s+(?:tokens?|context|parameters?))',
        r'**\1**', text, flags=_re.IGNORECASE
    )
    # Large numbers with units: 1.5 billion users, 100 million DAU
    text = _re.sub(
        r'([\d,.]+\s+(?:billion|million|thousand)\s+(?:users?|DAU|MAU|downloads?|parameters?))',
        r'**\1**', text, flags=_re.IGNORECASE
    )
    # Avoid double-bolding: collapse **...**...**...** overlaps
    text = _re.sub(r'\*\*\s*\*\*', '', text)
    return text


def _generate_why_it_matters(title, summary):
    """Generate a heuristic 'Why it matters' line for a top AI story."""
    text = (title + " " + summary).lower()
    if any(w in text for w in ["open source", "open-source", "apache", "mit license"]):
        return "Why it matters: Open-sourcing pushes the frontier accessible to all builders, not just big labs."
    if any(w in text for w in ["benchmark", "elo", "mmlu", "state-of-the-art", "sota"]):
        return "Why it matters: New benchmarks reset expectations for what AI models can do in production."
    if any(w in text for w in ["regulation", "executive order", "eu ai act", "congress", "parliament"]):
        return "Why it matters: Regulatory moves shape what companies can build and how fast they can ship."
    if any(w in text for w in ["agent", "agentic", "autonomous"]):
        return "Why it matters: Agentic AI is moving from demos to real workflows, changing how work gets done."
    if any(w in text for w in ["safety", "alignment", "guardrail", "red team"]):
        return "Why it matters: Safety progress determines how quickly frontier models reach mainstream users."
    if any(w in text for w in ["partnership", "deal", "collaboration"]):
        return "Why it matters: Strategic partnerships signal where the industry's center of gravity is shifting."
    if any(w in text for w in ["launch", "release", "announce", "unveil", "introduce"]):
        return "Why it matters: New releases force competitors to respond and give builders more options."
    return ""


def _generate_funding_why_it_matters(title, summary):
    """Generate a heuristic 'Why it matters' line for a funding story."""
    text = (title + " " + summary).lower()
    if any(w in text for w in ["billion", "$1b", "$2b", "$5b", "$10b"]):
        return "Why it matters: Mega-rounds signal investor conviction that AI infrastructure is a generational bet."
    if any(w in text for w in ["seed", "pre-seed", "early"]):
        return "Why it matters: Early-stage bets reveal where smart money sees the next breakout category."
    if any(w in text for w in ["acquisition", "acquire", "acqui-hire"]):
        return "Why it matters: Acqui-hires and acquisitions show which capabilities big tech can't build fast enough internally."
    if any(w in text for w in ["ipo", "public", "listing"]):
        return "Why it matters: IPO moves set the valuation benchmark for the entire AI startup ecosystem."
    return "Why it matters: Where capital flows today shapes what products ship tomorrow."


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
    for idx, a in enumerate(general_articles[:7]):
        title = a["title"].strip()
        summary = (a.get("summary") or "").strip()
        url = a.get("url", "")
        source = a.get("source", "")
        if summary:
            # Use up to 3-4 sentences for richer summaries
            sentences = summary.split(". ")
            rich_summary = ". ".join(sentences[:4]).rstrip(".")
            if len(rich_summary) > 400:
                rich_summary = rich_summary[:397] + "..."
            # Bold metrics in the summary
            rich_summary = _bold_metrics_in_markdown(rich_summary)
            lines.append(f"- **{title}** — {rich_summary}. [{source}]({url})")
        else:
            lines.append(f"- **{title}** [{source}]({url})")
        # Add "Why it matters" for top 3 stories
        if idx < 3:
            why = _generate_why_it_matters(title, summary)
            if why:
                lines.append(f"  - {why}")
        lines.append("")
    if not general_articles:
        lines.append("Quiet day on the feeds. Check back tomorrow.")
        lines.append("")

    # Funding & Deals
    if funding_articles:
        lines.append("## Funding & Deals")
        lines.append("")
        for idx, a in enumerate(funding_articles[:4]):
            title = a["title"].strip()
            summary = (a.get("summary") or "").strip()
            url = a.get("url", "")
            source = a.get("source", "")
            if summary:
                sentences = summary.split(". ")
                rich_summary = ". ".join(sentences[:4]).rstrip(".")
                if len(rich_summary) > 400:
                    rich_summary = rich_summary[:397] + "..."
                rich_summary = _bold_metrics_in_markdown(rich_summary)
                lines.append(f"- **{title}** — {rich_summary}. [{source}]({url})")
            else:
                lines.append(f"- **{title}** [{source}]({url})")
            # Add "Why it matters" for funding stories
            why = _generate_funding_why_it_matters(title, summary)
            if why:
                lines.append(f"  - {why}")
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

    print(f"\n{NEWSLETTER_NAME} — Summarizer — {target_date}")
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
