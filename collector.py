#!/usr/bin/env python3
"""
Content collector for The AI Brief — fetches articles, podcasts, videos,
and events from configured sources.

Usage:
    python3 collector.py              # collect today's content
    python3 collector.py --dry-run    # fetch + display, don't save
    python3 collector.py --date 2026-03-02
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import date, datetime
from html.parser import HTMLParser

from config import (
    RSS_FEEDS, PODCAST_FEEDS, YOUTUBE_CHANNELS, EVENTS_CONFIG,
    EVENTS_KEYWORDS_INCLUDE, EVENTS_KEYWORDS_EXCLUDE, EVENTS_SPEAKER_SIGNALS,
    COLLECTED_DIR, SEEN_ARTICLES_FILE,
    REQUEST_TIMEOUT, MAX_RETRIES, USER_AGENT,
)


# ── HTTP helper ──────────────────────────────────────────────────────────────

def fetch_url(url, retries=None):
    """Fetch URL content with retry. Returns bytes or None."""
    if retries is None:
        retries = MAX_RETRIES
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"  [WARN] Failed to fetch {url}: {e}")
            return None


# ── RSS parsing ──────────────────────────────────────────────────────────────

def parse_rss(xml_text, max_items=10):
    """Parse RSS 2.0 or Atom feed XML. Returns list of article dicts."""
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"  [WARN] XML parse error: {e}")
        return []

    # Atom namespace
    atom_ns = "{http://www.w3.org/2005/Atom}"

    # Try RSS 2.0 first: /rss/channel/item
    items = root.findall(".//item")
    if items:
        for item in items[:max_items]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            # Clean HTML from description
            desc = strip_html(desc)[:300]
            articles.append({
                "title": title,
                "url": link,
                "summary": desc,
                "date": parse_date_str(pub_date),
            })
        return articles

    # Try Atom: /feed/entry
    entries = root.findall(f"{atom_ns}entry")
    if not entries:
        entries = root.findall("entry")
    for entry in entries[:max_items]:
        title = (entry.findtext(f"{atom_ns}title") or entry.findtext("title") or "").strip()
        # Atom link — prefer rel="alternate", fall back to first with href
        link = ""
        for link_el in entry.findall(f"{atom_ns}link") + entry.findall("link"):
            href = link_el.get("href", "")
            rel = link_el.get("rel", "")
            if href and rel == "alternate":
                link = href
                break
            if href and not link:
                link = href
        summary = (entry.findtext(f"{atom_ns}summary") or entry.findtext("summary")
                   or entry.findtext(f"{atom_ns}content") or entry.findtext("content") or "").strip()
        summary = strip_html(summary)[:300]
        updated = (entry.findtext(f"{atom_ns}updated") or entry.findtext("updated")
                   or entry.findtext(f"{atom_ns}published") or entry.findtext("published") or "").strip()
        articles.append({
            "title": title,
            "url": link,
            "summary": summary,
            "date": parse_date_str(updated),
        })

    return articles


# ── HTML stripping ───────────────────────────────────────────────────────────

class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)

    def get_text(self):
        return " ".join("".join(self.text).split())


def strip_html(html_str):
    """Remove HTML tags, return plain text."""
    stripper = HTMLStripper()
    try:
        stripper.feed(html_str)
    except Exception:
        return html_str
    return stripper.get_text()


# ── Date parsing ─────────────────────────────────────────────────────────────

def parse_date_str(date_str):
    """Best-effort date string → YYYY-MM-DD."""
    if not date_str:
        return date.today().isoformat()
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",   # RSS pubDate
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",         # Atom / ISO
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d",
    ]:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date.today().isoformat()


# ── Deduplication ────────────────────────────────────────────────────────────

def load_seen_articles():
    """Load set of previously seen article URLs."""
    if SEEN_ARTICLES_FILE.exists():
        with open(SEEN_ARTICLES_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen_articles(seen):
    """Save seen article URLs."""
    with open(SEEN_ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)


# ── Source fetchers ──────────────────────────────────────────────────────────

def fetch_rss_feeds():
    """Fetch all configured RSS feeds. Returns list of article dicts."""
    all_articles = []
    for source_name, feed_info in RSS_FEEDS.items():
        print(f"  Fetching {source_name}...")
        raw = fetch_url(feed_info["url"])
        if not raw:
            continue
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = raw.decode("latin-1", errors="replace")
        articles = parse_rss(text)
        for a in articles:
            a["source"] = source_name
            a["type"] = "article"
        all_articles.extend(articles)
        print(f"    Got {len(articles)} articles")
    return all_articles


def fetch_podcasts():
    """Fetch latest podcast episodes from configured feeds."""
    all_episodes = []
    for name, feed_info in PODCAST_FEEDS.items():
        print(f"  Fetching {name}...")
        raw = fetch_url(feed_info["url"])
        if not raw:
            continue
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = raw.decode("latin-1", errors="replace")
        episodes = parse_rss(text, max_items=feed_info.get("max_episodes", 2))
        for ep in episodes:
            ep["source"] = name
            ep["type"] = "podcast"
        all_episodes.extend(episodes)
        print(f"    Got {len(episodes)} episodes")
    return all_episodes


def fetch_youtube_videos():
    """Fetch latest videos from configured YouTube channels via RSS."""
    all_videos = []
    for name, channel_info in YOUTUBE_CHANNELS.items():
        print(f"  Fetching {name}...")
        raw = fetch_url(channel_info["url"])
        if not raw:
            continue
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = raw.decode("latin-1", errors="replace")
        videos = parse_rss(text, max_items=channel_info.get("max_videos", 2))
        for v in videos:
            v["source"] = name
            v["type"] = "video"
        all_videos.extend(videos)
        print(f"    Got {len(videos)} videos")
    return all_videos


def fetch_events():
    """Fetch AI/tech/startup events from Eventbrite and Luma."""
    all_events = []

    # Eventbrite — HTML scraping (often returns 0 due to JS rendering)
    eventbrite_urls = EVENTS_CONFIG.get("eventbrite_urls", [])
    for location in EVENTS_CONFIG["locations"]:
        for url_pattern in eventbrite_urls:
            url = url_pattern.format(location=location.lower())
            print(f"  Fetching Eventbrite events in {location}...")
            raw = fetch_url(url, retries=1)
            if not raw:
                continue
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                continue
            events = parse_eventbrite_html(text, location)
            all_events.extend(events)
            print(f"    Got {len(events)} raw events")

    # Luma — parse __NEXT_DATA__ JSON from discover pages
    luma_urls = EVENTS_CONFIG.get("luma_discover_urls", [])
    seen_luma = set()  # dedup across location/tag combos

    for location in EVENTS_CONFIG["locations"]:
        for url_pattern in luma_urls:
            url = url_pattern.format(location=location.lower())
            print(f"  Fetching Luma events near {location}...")
            luma_events = fetch_luma_nextdata(url, location)
            for ev in luma_events:
                key = ev.get("url", ev.get("title"))
                if key not in seen_luma:
                    seen_luma.add(key)
                    all_events.append(ev)
            print(f"    Got {len(luma_events)} events")

    # Filter for relevant events
    before_count = len(all_events)
    all_events = filter_events(all_events)
    print(f"  Filtered {before_count} → {len(all_events)} relevant events")
    return all_events


def fetch_luma_nextdata(url, location):
    """Fetch lu.ma discover page and extract events from __NEXT_DATA__ JSON."""
    import json as _json
    import re as _re

    raw = fetch_url(url, retries=1)
    if not raw:
        return []

    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return []

    # Extract __NEXT_DATA__ script tag
    m = _re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', text)
    if not m:
        return []

    try:
        data = _json.loads(m.group(1))
    except _json.JSONDecodeError:
        return []

    page_props = data.get("props", {}).get("pageProps", {}).get("initialData", {})
    featured = page_props.get("featured_place", {})
    raw_events = featured.get("events", [])

    events = []
    for entry in raw_events[:15]:
        ev = entry.get("event", entry)
        name = ev.get("name", "").strip()
        slug = ev.get("url", "")
        start = ev.get("start_at", "")
        geo_city = ev.get("geo_address_info", {}).get("city", location)

        if not name:
            continue

        event_url = f"https://lu.ma/{slug}" if slug else ""
        date_str = start[:10] if start else ""

        actual_city = geo_city or location
        events.append({
            "title": name,
            "url": event_url,
            "summary": f"Tech/AI event in {actual_city}",
            "date": date_str,
            "source": f"Luma ({actual_city})",
            "type": "event",
        })

    return events


class EventbriteParser(HTMLParser):
    """Extract event titles, URLs, and description snippets from Eventbrite search results."""

    def __init__(self):
        super().__init__()
        self.events = []
        self._in_card = False
        self._in_link = False
        self._in_desc = False
        self._current = {}
        self._tag_stack = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")

        # Detect event card containers
        if "event-card" in cls and "event-card-link" not in cls:
            self._in_card = True
            self._current = {"url": "", "title": "", "description": ""}

        # Detect event card link (title)
        if tag == "a" and "event-card-link" in cls:
            self._in_link = True
            self._current["url"] = attrs_dict.get("href", "")

        # Detect description/subtitle areas
        if self._in_card and tag in ("p", "span") and any(
            kw in cls for kw in ["card-text", "subtitle", "desc", "summary"]
        ):
            self._in_desc = True

        self._tag_stack.append(tag)

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        if self._in_link:
            self._current["title"] += " " + text
        elif self._in_desc and self._in_card:
            self._current["description"] += " " + text
        elif self._in_card and not self._current.get("title"):
            # Capture text in card even without specific class
            pass

    def handle_endtag(self, tag):
        if self._tag_stack:
            self._tag_stack.pop()

        if tag == "a" and self._in_link:
            self._in_link = False

        if tag in ("p", "span") and self._in_desc:
            self._in_desc = False

        # Close card on div end when at top-level card
        if tag == "div" and self._in_card and not self._tag_stack:
            self._in_card = False
            if self._current.get("title"):
                self._current["title"] = self._current["title"].strip()
                self._current["description"] = self._current["description"].strip()
                self.events.append(self._current)
            self._current = {}


def parse_eventbrite_html(html_text, location):
    """Parse Eventbrite search results HTML for event cards."""
    parser = EventbriteParser()
    try:
        parser.feed(html_text)
    except Exception:
        pass
    events = []
    for ev in parser.events[:15]:  # grab more, filter later
        events.append({
            "title": ev["title"],
            "url": ev["url"],
            "summary": ev.get("description") or f"AI event in {location}",
            "date": "",
            "source": f"Eventbrite ({location})",
            "type": "event",
        })
    return events


# ── Event filtering ─────────────────────────────────────────────────────

def filter_events(events):
    """Filter and score events for AI relevance. Returns top 5 by score."""
    filtered = []
    for ev in events:
        text = (ev.get("title", "") + " " + ev.get("summary", "")).lower()

        # Must contain at least one include keyword
        has_include = any(kw.lower() in text for kw in EVENTS_KEYWORDS_INCLUDE)
        if not has_include:
            continue

        # Reject if contains any exclude keyword
        has_exclude = any(kw.lower() in text for kw in EVENTS_KEYWORDS_EXCLUDE)
        if has_exclude:
            continue

        # Score: +1 per include keyword match, +2 per speaker signal match
        score = sum(1 for kw in EVENTS_KEYWORDS_INCLUDE if kw.lower() in text)
        score += sum(2 for sig in EVENTS_SPEAKER_SIGNALS if sig.lower() in text)
        ev["_score"] = score
        filtered.append(ev)

    # Sort by score descending, keep top 8
    filtered.sort(key=lambda e: e.get("_score", 0), reverse=True)
    result = []
    for ev in filtered[:8]:
        ev.pop("_score", None)
        result.append(ev)
    return result


# ── Main collector ───────────────────────────────────────────────────────────

def collect_all(target_date=None):
    """Orchestrate all fetchers, dedup, save collected data."""
    if target_date is None:
        target_date = date.today().isoformat()

    print(f"\nThe AI Brief — Collector — {target_date}")
    print("=" * 50)

    seen = load_seen_articles()
    all_items = []

    # Fetch all sources
    print("\n[RSS Feeds]")
    all_items.extend(fetch_rss_feeds())

    print("\n[Podcasts]")
    all_items.extend(fetch_podcasts())

    print("\n[YouTube]")
    all_items.extend(fetch_youtube_videos())

    print("\n[Events]")
    all_items.extend(fetch_events())

    # Dedup by URL
    new_items = []
    for item in all_items:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            new_items.append(item)

    print(f"\n  Total fetched: {len(all_items)}")
    print(f"  New (deduped): {len(new_items)}")

    return target_date, new_items, seen


def save_collected(target_date, items, seen):
    """Save collected items and update seen articles."""
    output_file = COLLECTED_DIR / f"{target_date}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    print(f"  Saved to {output_file}")
    save_seen_articles(seen)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv
    target_date = None

    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            target_date = sys.argv[idx + 1]

    target_date, items, seen = collect_all(target_date)

    if dry_run:
        print("\n(Dry run — not saving)")
        for item in items[:10]:
            print(f"  [{item['type']}] [{item['source']}] {item['title'][:60]}")
    else:
        save_collected(target_date, items, seen)


if __name__ == "__main__":
    main()
