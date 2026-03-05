#!/usr/bin/env python3
"""
Publisher for The AI Brief — converts markdown draft to HTML site page,
sends email to subscribers, and updates site index/archive.

Usage:
    python3 publisher.py                        # publish today's draft
    python3 publisher.py --date 2026-03-02
    python3 publisher.py --dry-run              # render HTML, don't send email
    python3 publisher.py --email-only           # send email, skip site
    python3 publisher.py --site-only            # update site, skip email
"""

import os
import re
import smtplib
import sys
from collections import OrderedDict
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from config import (
    DRAFTS_DIR, SITE_DIR, ISSUES_DIR, EMAIL,
    NEWSLETTER_NAME, OXFORD_BLUE, FORMSPREE_ENDPOINT,
)
from subscribe import get_active_emails


# ── Markdown → HTML (for email, kept simple) ─────────────────────────────────

def markdown_to_html(md):
    """Convert markdown to HTML using stdlib re. For email body."""
    lines = md.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        if stripped in ("---", "***", "___"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<hr>")
            continue

        if stripped.startswith("# ") and not stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1>{inline_format(stripped[2:])}</h1>")
            continue
        if stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{inline_format(stripped[3:])}</h2>")
            continue
        if stripped.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{inline_format(stripped[4:])}</h3>")
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"  <li>{inline_format(stripped[2:])}</li>")
            continue

        m = re.match(r"^\d+\.\s+(.*)", stripped)
        if m:
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"  <li>{inline_format(m.group(1))}</li>")
            continue

        if in_list and stripped:
            html_lines.append("</ul>")
            in_list = False

        if not stripped:
            continue

        html_lines.append(f"<p>{inline_format(stripped)}</p>")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def inline_format(text):
    """Handle bold, italic, links, and code in inline text."""
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text


# ── Markdown parser for site (structured) ────────────────────────────────────

SECTION_TAG_MAP = {
    "Top AI Stories": ("news", "blue"),
    "Funding & Deals": ("funding", "green"),
    "Podcasts Worth Your Commute": ("podcast", "purple"),
    "Events Near You": ("event", "orange"),
    "Videos Going Viral": ("video", "red"),
}


def parse_markdown_sections(md):
    """Parse newsletter markdown into structured sections and items."""
    sections = []
    current_section = None

    for line in md.split("\n"):
        stripped = line.strip()

        if stripped.startswith("# ") and not stripped.startswith("## "):
            continue
        if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
            continue  # skip date line

        if stripped.startswith("## "):
            heading = stripped[3:].strip()
            tag_info = SECTION_TAG_MAP.get(heading, ("news", "gray"))
            current_section = {
                "heading": heading,
                "tag": tag_info[0],
                "color": tag_info[1],
                "items": [],
                "text": [],
            }
            sections.append(current_section)
            continue

        if stripped in ("---", "***", "___", ""):
            continue

        if current_section is None:
            continue

        if stripped.startswith("- "):
            item = _parse_item(stripped[2:])
            if item:
                current_section["items"].append(item)
            else:
                current_section["text"].append(stripped[2:])
            continue

        current_section["text"].append(stripped)

    return sections


def _parse_item(text):
    """Parse: **Title** — summary. [Source](url)"""
    title_match = re.match(r'\*\*(.+?)\*\*\s*(.*)', text)
    if not title_match:
        return None

    title = title_match.group(1).strip()
    rest = title_match.group(2).strip()
    rest = re.sub(r'^[—–-]\s*', '', rest)

    source = ""
    url = ""
    link_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', rest)
    if link_match:
        source = link_match.group(1)
        url = link_match.group(2)
        summary = rest[:link_match.start()].strip().rstrip('.').strip()
    else:
        summary = rest.rstrip('.').strip()

    # Extract keywords for tags
    tags = _extract_tags(title + " " + summary)

    return {
        "title": title,
        "summary": summary,
        "source": source,
        "url": url,
        "tags": tags,
    }


def _extract_tags(text):
    """Extract keyword tags from text for tag cloud display."""
    tag_keywords = {
        # Companies
        "openai": ("openai", "gray"),
        "anthropic": ("anthropic", "gray"),
        "google": ("google", "gray"),
        "meta": ("meta", "gray"),
        "microsoft": ("microsoft", "gray"),
        "nvidia": ("nvidia", "gray"),
        "deepmind": ("deepmind", "gray"),
        "amazon": ("amazon", "gray"),
        "apple": ("apple", "gray"),
        "softbank": ("softbank", "gray"),
        # Models
        "gpt": ("gpt", "green"),
        "claude": ("claude", "green"),
        "gemini": ("gemini", "green"),
        "llama": ("llama", "green"),
        "codex": ("codex", "green"),
        # Topics
        "funding": ("funding", "blue"),
        "investment": ("investment", "blue"),
        "series": ("series-round", "blue"),
        "valuation": ("valuation", "blue"),
        "startup": ("startup", "blue"),
        "acquisition": ("acquisition", "blue"),
        "ai safety": ("ai-safety", "orange"),
        "regulation": ("regulation", "orange"),
        "robotics": ("robotics", "purple"),
        "autonomous": ("autonomous", "purple"),
        "agent": ("agents", "purple"),
        "multimodal": ("multimodal", "purple"),
    }

    text_lower = text.lower()
    found = []
    seen = set()
    for keyword, (tag_name, color) in tag_keywords.items():
        if keyword in text_lower and tag_name not in seen:
            found.append({"name": tag_name, "color": color})
            seen.add(tag_name)

    return found


def _esc(text):
    """HTML-escape."""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ── Site page builders ───────────────────────────────────────────────────────

def build_header(home_prefix=""):
    """smol.ai-style header: logo box left, nav links right."""
    subscribe_href = f"{home_prefix}index.html#subscribe" if home_prefix else "#subscribe"
    return f"""<div class="site-header">
    <a class="logo" href="{home_prefix}index.html">{NEWSLETTER_NAME}</a>
    <nav>
      <a href="{subscribe_href}">subscribe</a>
      <span class="sep">/</span>
      <a href="{home_prefix}archive.html">issues</a>
      <span class="sep">/</span>
      <a href="{home_prefix}archive.html#tags">tags</a>
    </nav>
  </div>"""


def build_timeline_entry(item, section, date_short):
    """Build one timeline <li> entry with expandable card body."""
    title_html = _esc(item["title"])
    if item["url"]:
        title_link = f'<a href="{_esc(item["url"])}">{title_html}</a>'
    else:
        title_link = title_html

    # Tags cloud
    tags_html = ""
    if item.get("tags"):
        pills = []
        for t in item["tags"]:
            pills.append(f'<span class="tag-pill {t["color"]}">{_esc(t["name"])}</span>')
        # Add the section tag
        pills.append(f'<span class="tag-pill {section["color"]}">{_esc(section["tag"])}</span>')
        tags_html = f'<div class="tags-cloud">{"".join(pills)}</div>'
    else:
        tags_html = f'<div class="tags-cloud"><span class="tag-pill {section["color"]}">{_esc(section["tag"])}</span></div>'

    # Detail text
    detail_html = ""
    if item["summary"]:
        # Make bold words in summary
        summary_formatted = inline_format(item["summary"])
        detail_html = f'<div class="detail-text"><p>{summary_formatted}</p></div>'

    source_html = ""
    if item["source"]:
        if item["url"]:
            source_html = f'<div class="source-label">Source: <a href="{_esc(item["url"])}">{_esc(item["source"])}</a></div>'
        else:
            source_html = f'<div class="source-label">Source: {_esc(item["source"])}</div>'

    has_body = tags_html or detail_html or source_html
    has_class = ' has-content' if has_body else ''

    body_html = ""
    if has_body:
        body_html = f"""
    <div class="tl-body">
      <button class="close-btn" onclick="this.closest('.tl-entry').classList.remove('expanded')">&times;</button>
      {tags_html}
      {detail_html}
      {source_html}
    </div>"""

    return f"""  <li class="tl-entry{has_class}">
    <div class="tl-header" onclick="this.parentElement.classList.toggle('expanded')">
      <span class="tl-date">{date_short}</span>
      <span class="tl-title">{title_link}</span>
      <span class="tl-arrow">&rarr;</span>
    </div>{body_html}
  </li>"""


def build_timeline_text_entry(text, section, date_short):
    """Build a simple text timeline entry (for fallback messages)."""
    return f"""  <li class="tl-entry">
    <div class="tl-header">
      <span class="tl-date">{date_short}</span>
      <span class="tl-title">{inline_format(text)}</span>
    </div>
  </li>"""


def markdown_to_timeline_html(md, target_date):
    """Render parsed markdown as vertical timeline with expandable cards."""
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        date_short = dt.strftime("%b %d")
    except ValueError:
        date_short = target_date

    sections = parse_markdown_sections(md)
    html_parts = ['<ol class="timeline">']

    for section in sections:
        html_parts.append(f'  <li class="tl-section">{_esc(section["heading"])}</li>')

        if section["items"]:
            for item in section["items"]:
                html_parts.append(build_timeline_entry(item, section, date_short))
        elif section["text"]:
            text = " ".join(section["text"])
            html_parts.append(build_timeline_text_entry(text, section, date_short))

    html_parts.append('</ol>')
    return "\n".join(html_parts)


def markdown_to_issue_html(md, target_date):
    """Render markdown as two-column issue page with TOC sidebar + rich content."""
    sections = parse_markdown_sections(md)

    # Build TOC
    toc_items = []
    for i, section in enumerate(sections):
        slug = re.sub(r'[^a-z0-9]+', '-', section["heading"].lower()).strip('-')
        toc_items.append(f'    <li><a href="#{slug}">{_esc(section["heading"])}</a>')
        # Sub-items
        if section["items"]:
            toc_items.append(f'      <div class="toc-sub">')
            for j, item in enumerate(section["items"][:5]):
                sub_slug = f"{slug}-{j}"
                title_short = item["title"][:45] + ("..." if len(item["title"]) > 45 else "")
                toc_items.append(f'        <a href="#{sub_slug}">{_esc(title_short)}</a>')
            toc_items.append(f'      </div>')
        toc_items.append(f'    </li>')

    toc_html = "\n".join(toc_items)

    # Collect all tags for top-of-page tag cloud
    all_tags = {"SECTIONS": [], "SOURCES": [], "TOPICS": []}
    source_set = set()
    topic_set = set()

    for section in sections:
        all_tags["SECTIONS"].append({"name": section["tag"], "color": section["color"]})
        for item in section["items"]:
            if item["source"] and item["source"] not in source_set:
                source_set.add(item["source"])
                all_tags["SOURCES"].append({"name": item["source"].lower().replace(" ", "-"), "color": "gray"})
            for t in item.get("tags", []):
                if t["name"] not in topic_set:
                    topic_set.add(t["name"])
                    all_tags["TOPICS"].append(t)

    # Build tags section
    tags_section_parts = []
    for category, tags in all_tags.items():
        if tags:
            pills = " ".join(f'<span class="tag-pill {t["color"]}">{_esc(t["name"])}</span>' for t in tags)
            tags_section_parts.append(f'<div class="tag-group"><div class="tag-category">{category}</div>{pills}</div>')

    tags_section_html = "\n    ".join(tags_section_parts)

    # Build content
    content_parts = []
    for i, section in enumerate(sections):
        slug = re.sub(r'[^a-z0-9]+', '-', section["heading"].lower()).strip('-')
        content_parts.append(f'<h2 id="{slug}">{_esc(section["heading"])}</h2>')

        if section["items"]:
            for j, item in enumerate(section["items"]):
                sub_slug = f"{slug}-{j}"
                title_html = _esc(item["title"])
                if item["url"]:
                    title_html = f'<a href="{_esc(item["url"])}">{title_html}</a>'

                content_parts.append(f'<h3 id="{sub_slug}">{title_html}</h3>')

                if item["summary"]:
                    summary_html = inline_format(item["summary"])
                    content_parts.append(f'<p>{summary_html}</p>')

                if item["source"]:
                    if item["url"]:
                        content_parts.append(f'<p class="source-label">Source: <a href="{_esc(item["url"])}">{_esc(item["source"])}</a></p>')
                    else:
                        content_parts.append(f'<p class="source-label">Source: {_esc(item["source"])}</p>')

        elif section["text"]:
            for t in section["text"]:
                content_parts.append(f'<p>{inline_format(t)}</p>')

    content_html = "\n    ".join(content_parts)

    return f"""<div class="issue-tags" id="tags">
    <div class="issue-tags-header">
      <div></div>
      <button class="tags-toggle-btn" onclick="this.closest('.issue-tags').classList.toggle('hidden-tags')">show/hide tags</button>
    </div>
    {tags_section_html}
  </div>

  <div class="issue-layout">
    <aside class="toc-sidebar">
      <div class="toc-toggle" onclick="this.parentElement.classList.toggle('collapsed')">TABLE OF CONTENTS</div>
      <ul class="toc-list">
{toc_html}
      </ul>
    </aside>

    <div class="issue-content">
    {content_html}
    </div>
  </div>"""


# ── Email HTML (inline CSS, unchanged) ───────────────────────────────────────

def build_email_html(content_html, target_date):
    """Build inline-CSS HTML email with Oxford blue branding."""
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        date_display = dt.strftime("%A, %B %d, %Y")
    except ValueError:
        date_display = target_date

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:680px;margin:0 auto;background:#ffffff;">
    <div style="background:{OXFORD_BLUE};padding:24px 32px;text-align:center;">
      <h1 style="margin:0;color:#ffffff;font-size:28px;letter-spacing:1px;">{NEWSLETTER_NAME}</h1>
      <p style="margin:8px 0 0;color:#a0b4c8;font-size:14px;">{date_display}</p>
    </div>
    <div style="padding:24px 32px;line-height:1.6;color:#333;">
      {content_html}
    </div>
    <div style="background:#f0f2f5;padding:20px 32px;text-align:center;font-size:13px;color:#666;">
      <p style="margin:0;">You're receiving this because you subscribed to {NEWSLETTER_NAME}.</p>
    </div>
  </div>
</body>
</html>"""


# ── Navigation helpers ───────────────────────────────────────────────────────

def build_date_picker(current_date=None, link_prefix=""):
    """Build a month-tabbed date picker strip with clickable date pills.

    current_date: YYYY-MM-DD of the currently viewed issue (highlighted)
    link_prefix:  "../" for issue pages, "" for top-level pages
    """
    from calendar import monthrange

    all_dates = sorted(
        f.stem for f in ISSUES_DIR.glob("*.html")
        if re.match(r"\d{4}-\d{2}-\d{2}", f.stem)
    )
    if not all_dates:
        return ""

    issue_set = set(all_dates)

    # Group by year-month
    months = OrderedDict()
    for d in reversed(all_dates):  # newest first
        ym = d[:7]  # YYYY-MM
        if ym not in months:
            months[ym] = []
        months[ym].append(d)

    current_ym = current_date[:7] if current_date else list(months.keys())[0]

    # Build month tabs
    tabs_html = []
    rows_html = []
    for ym in months:
        try:
            dt = datetime.strptime(ym + "-01", "%Y-%m-%d")
            month_label = dt.strftime("%b %Y")
        except ValueError:
            month_label = ym

        active = " active" if ym == current_ym else ""
        tabs_html.append(
            f'<span class="dp-month-tab{active}" data-month="{ym}">{month_label}</span>'
        )

        # Build date pills for every day in the month
        year, mon = int(ym[:4]), int(ym[5:7])
        _, num_days = monthrange(year, mon)
        pills = []
        for day in range(1, num_days + 1):
            day_str = f"{ym}-{day:02d}"
            if day_str in issue_set:
                is_current = " current" if day_str == current_date else ""
                href = f"{link_prefix}issues/{day_str}.html" if link_prefix != "ISSUE" else f"{day_str}.html"
                pills.append(
                    f'<a class="dp-date{is_current}" href="{href}">{day}</a>'
                )
            else:
                pills.append(f'<span class="dp-date empty">{day}</span>')

        rows_html.append(
            f'<div class="dp-dates-row{active}" data-month="{ym}">{"".join(pills)}</div>'
        )

    picker_js = """<script>
document.querySelectorAll('.dp-month-tab').forEach(function(tab) {
  tab.addEventListener('click', function() {
    var m = this.dataset.month;
    var picker = this.closest('.date-picker');
    picker.querySelectorAll('.dp-month-tab').forEach(function(t) { t.classList.remove('active'); });
    picker.querySelectorAll('.dp-dates-row').forEach(function(r) { r.classList.remove('active'); });
    this.classList.add('active');
    picker.querySelector('.dp-dates-row[data-month="'+m+'"]').classList.add('active');
  });
});
</script>"""

    return f"""<div class="date-picker">
  <div class="dp-months">{"".join(tabs_html)}</div>
  {"".join(rows_html)}
</div>
{picker_js}"""


def get_adjacent_dates(target_date):
    """Find prev/next issue dates by scanning site/issues/."""
    all_dates = sorted(
        f.stem for f in ISSUES_DIR.glob("*.html")
        if re.match(r"\d{4}-\d{2}-\d{2}", f.stem)
    )
    prev_date = next_date = None
    if target_date in all_dates:
        idx = all_dates.index(target_date)
        if idx > 0:
            prev_date = all_dates[idx - 1]
        if idx < len(all_dates) - 1:
            next_date = all_dates[idx + 1]
    return prev_date, next_date


def format_nav_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%b %-d, %Y")
    except ValueError:
        return date_str


def build_issue_nav(target_date):
    prev_date, next_date = get_adjacent_dates(target_date)
    prev_link = (f'<a href="{prev_date}.html">&larr; {format_nav_date(prev_date)}</a>'
                 if prev_date else '<span class="nav-placeholder">&larr;</span>')
    next_link = (f'<a href="{next_date}.html">{format_nav_date(next_date)} &rarr;</a>'
                 if next_date else '<span class="nav-placeholder">&rarr;</span>')
    return f'<div class="issue-nav">{prev_link}{next_link}</div>'


# ── Page JS ──────────────────────────────────────────────────────────────────

SITE_JS = """<script>
// Toggle timeline card expansion
document.querySelectorAll('.tl-entry .tl-header').forEach(function(el) {
  el.addEventListener('click', function(e) {
    if (e.target.tagName === 'A') return;
    this.parentElement.classList.toggle('expanded');
  });
});

// Smooth TOC scroll
document.querySelectorAll('.toc-list a').forEach(function(a) {
  a.addEventListener('click', function(e) {
    var target = document.querySelector(this.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      history.replaceState(null, '', this.getAttribute('href'));
    }
  });
});

// Filter titles on index
var filterInput = document.getElementById('regex-filter');
if (filterInput) {
  filterInput.addEventListener('input', function() {
    var pattern;
    try { pattern = new RegExp(this.value, 'i'); } catch(e) { return; }
    document.querySelectorAll('.tl-entry').forEach(function(li) {
      var title = li.querySelector('.tl-title');
      if (title) {
        li.style.display = pattern.test(title.textContent) ? '' : 'none';
      }
    });
  });
}
</script>"""


# ── Full page builders ───────────────────────────────────────────────────────

def build_site_page(content_html, target_date, md_content=None):
    """Build issue page with smol.ai-style TOC layout."""
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        date_display = dt.strftime("%A, %B %d, %Y")
    except ValueError:
        date_display = target_date

    header = build_header(home_prefix="../")
    issue_nav = build_issue_nav(target_date)
    date_picker = build_date_picker(current_date=target_date, link_prefix="ISSUE")

    if md_content:
        body_html = markdown_to_issue_html(md_content, target_date)
    else:
        body_html = f'<div class="issue-layout"><div class="issue-content">{content_html}</div></div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{NEWSLETTER_NAME} — {date_display}</title>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  {header}
  {date_picker}
  {issue_nav}
  <div style="max-width:960px;margin:0 auto;padding:0 32px;">
    <h1 style="font-size:1.1rem;color:#888;font-weight:400;margin:20px 0 4px;">{date_display}</h1>
  </div>
  {body_html}
  {issue_nav}
  <footer>
    <a href="../index.html">Home</a> &middot; <a href="../archive.html">All Issues</a>
  </footer>
  {SITE_JS}
</body>
</html>"""


def build_placeholder_page(target_date):
    """Placeholder for dates without content."""
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        date_display = dt.strftime("%A, %B %d, %Y")
    except ValueError:
        date_display = target_date

    header = build_header(home_prefix="../")
    issue_nav = build_issue_nav(target_date)
    date_picker = build_date_picker(current_date=target_date, link_prefix="ISSUE")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{NEWSLETTER_NAME} — {date_display}</title>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  {header}
  {date_picker}
  {issue_nav}
  <div class="placeholder-notice">
    <p>No issue published for {date_display}.</p>
    <p class="subtitle">Check the <a href="../archive.html">archive</a> for available issues.</p>
  </div>
  {issue_nav}
  <footer>
    <a href="../index.html">Home</a> &middot; <a href="../archive.html">All Issues</a>
  </footer>
</body>
</html>"""


# ── Index page ───────────────────────────────────────────────────────────────

def get_recent_issue_dates(exclude=None, limit=5):
    all_dates = sorted(
        (f.stem for f in ISSUES_DIR.glob("*.html")
         if re.match(r"\d{4}-\d{2}-\d{2}", f.stem)),
        reverse=True,
    )
    result = []
    for d in all_dates:
        if d != exclude:
            result.append(d)
        if len(result) >= limit:
            break
    return result


def get_all_issue_dates():
    """Get all issue dates sorted descending."""
    return sorted(
        (f.stem for f in ISSUES_DIR.glob("*.html")
         if re.match(r"\d{4}-\d{2}-\d{2}", f.stem)),
        reverse=True,
    )


def update_index_page(timeline_html, target_date, md_content=None):
    """Regenerate index with smol.ai-style: title bar, filter, timeline, subscribe."""
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        date_display = dt.strftime("%A, %B %d, %Y")
    except ValueError:
        date_display = target_date

    formspree_action = f"https://formspree.io/f/{FORMSPREE_ENDPOINT}" if FORMSPREE_ENDPOINT else "#"
    header = build_header()
    date_picker = build_date_picker(current_date=target_date, link_prefix="")

    # Build a combined timeline: latest issue + recent dates with "show details" links
    all_dates = get_all_issue_dates()

    # Monthly summary section
    months = OrderedDict()
    for d in all_dates:
        ym = d[:7]
        if ym not in months:
            months[ym] = []
        months[ym].append(d)

    recent_timeline_parts = []
    for d in all_dates:
        if d == target_date:
            continue  # already shown as main timeline
        try:
            d_dt = datetime.strptime(d, "%Y-%m-%d")
            d_short = d_dt.strftime("%b %d")
            d_display = d_dt.strftime("%B %-d, %Y")
        except ValueError:
            d_short = d
            d_display = d
        recent_timeline_parts.append(f"""  <li class="tl-entry">
    <div class="tl-header" onclick="window.location.href='issues/{d}.html'">
      <span class="tl-date">{d_short}</span>
      <span class="tl-title"><a href="issues/{d}.html">{d_display}</a></span>
      <span class="tl-arrow">&rarr;</span>
    </div>
  </li>""")

    recent_timeline = "\n".join(recent_timeline_parts[:14])  # Show last 2 weeks

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{NEWSLETTER_NAME} — AI & Tech Digest</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  {header}
  {date_picker}

  <div class="subscribe-inline" id="subscribe">
    <form action="{formspree_action}" method="POST">
      <label>Subscribe:</label>
      <input type="email" name="email" placeholder="your@email.com" required>
      <input type="text" name="name" placeholder="Name">
      <button type="submit">Subscribe</button>
    </form>
  </div>

  <div class="title-bar">
    <h2>Last 30 days in AI & Tech</h2>
    <div class="filter-group">
      <label>Filter titles:</label>
      <input type="text" id="regex-filter" placeholder="regex...">
    </div>
    <a class="see-all" href="archive.html">See all issues</a>
  </div>

  <div class="timeline-container">
    {timeline_html}
    <ol class="timeline" style="margin-top:0;">
{recent_timeline}
    </ol>
  </div>

  <footer>
    <p>{NEWSLETTER_NAME} &middot; Oxford MBA 2025</p>
  </footer>
  {SITE_JS}
</body>
</html>"""

    with open(SITE_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"  Updated site/index.html")


# ── Archive page ─────────────────────────────────────────────────────────────

def extract_headlines_from_issue(filepath):
    """Extract headlines from an issue HTML file for archive summary."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            html = f.read()
        headlines = re.findall(r'class="tl-title"[^>]*>(?:<a[^>]*>)?(.+?)(?:</a>)?</span>', html)
        if not headlines:
            headlines = re.findall(r'<h3[^>]*>(?:<a[^>]*>)?(.+?)(?:</a>)?</h3>', html)
        if not headlines:
            headlines = re.findall(r"<strong>(.+?)</strong>", html)
        good = [h for h in headlines if len(h) > 10 and not h.startswith("No ")]
        return good[:3]
    except Exception:
        return []


def update_archive_page():
    """Regenerate archive with sidebar nav + monthly grouped entries."""
    issue_files = sorted(ISSUES_DIR.glob("*.html"), reverse=True)

    months = OrderedDict()
    for f in issue_files:
        date_str = f.stem
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            continue
        ym = date_str[:7]
        if ym not in months:
            months[ym] = []
        months[ym].append(f)

    header = build_header()

    # Sidebar nav
    nav_items = []
    current_year = None
    for ym in months:
        year = ym[:4]
        if year != current_year:
            current_year = year
            nav_items.append(f'<li><span class="year-label">{year}</span></li>')
        try:
            ym_dt = datetime.strptime(ym, "%Y-%m")
            month_name = ym_dt.strftime("%B")
            count = len(months[ym])
        except ValueError:
            month_name = ym
            count = len(months[ym])
        nav_items.append(f'<li><a class="month-link" href="#month-{ym}">{month_name} ({count})</a></li>')

    nav_html = "\n      ".join(nav_items)

    # Content sections
    sections_html = []
    for ym, files in months.items():
        try:
            ym_dt = datetime.strptime(ym, "%Y-%m")
            month_label = ym_dt.strftime("%B %Y")
        except ValueError:
            month_label = ym

        issue_count = len(files)
        count_label = f"{issue_count} issue{'s' if issue_count != 1 else ''}"

        top_headlines = []
        for f in files:
            top_headlines = extract_headlines_from_issue(f)
            if top_headlines:
                break
        summary = ""
        if top_headlines:
            truncated = [h[:50] + ("..." if len(h) > 50 else "") for h in top_headlines]
            summary = " &bull; ".join(truncated)

        items_html = []
        for f in files:
            date_str = f.stem
            try:
                d_dt = datetime.strptime(date_str, "%Y-%m-%d")
                d_short = d_dt.strftime("%b %d")
                d_display = d_dt.strftime("%B %-d, %Y")
            except ValueError:
                d_short = date_str
                d_display = date_str

            # Get headline preview
            headlines = extract_headlines_from_issue(f)
            preview = ""
            if headlines:
                preview = f'<span class="headline-preview">— {_esc(headlines[0][:40])}</span>'

            items_html.append(
                f'      <li>'
                f'<span class="date-badge">{d_short}</span>'
                f'<a href="issues/{f.name}">{d_display}</a>'
                f'{preview}'
                f'</li>'
            )

        items_joined = "\n".join(items_html)
        summary_line = f'\n    <p class="month-summary">{count_label} &mdash; {summary}</p>' if summary else f'\n    <p class="month-summary">{count_label}</p>'

        sections_html.append(f"""  <div class="archive-month" id="month-{ym}">
    <h2>{month_label}</h2>{summary_line}
    <ul class="archive-list">
{items_joined}
    </ul>
  </div>""")

    body = "\n\n".join(sections_html) if sections_html else "  <p>No issues yet.</p>"

    archive_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{NEWSLETTER_NAME} — Archive</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  {header}

  <div class="archive-container">
    <aside class="archive-nav">
      <h3>Quick Navigation</h3>
      <ul>
      {nav_html}
      </ul>
    </aside>

    <div class="archive-content">
{body}
    </div>
  </div>

  <footer>
    <a href="index.html">Home</a> &middot; <a href="#subscribe">Subscribe</a>
  </footer>
</body>
</html>"""

    with open(SITE_DIR / "archive.html", "w", encoding="utf-8") as f:
        f.write(archive_html)
    print(f"  Updated site/archive.html")


# ── Subject line ─────────────────────────────────────────────────────────────

def generate_subject_line(target_date, md_content):
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        day_str = dt.strftime("%A, %b %-d")
    except ValueError:
        day_str = target_date

    headlines = re.findall(r'\*\*(.+?)\*\*', md_content)
    teasers = []
    total_len = 0
    for h in headlines:
        if total_len + len(h) > 60:
            break
        teasers.append(h)
        total_len += len(h)

    teaser_str = ", ".join(teasers[:3]) if teasers else "Today's top AI stories"
    return f"{NEWSLETTER_NAME} — {day_str} | {teaser_str}"


# ── Email sending ────────────────────────────────────────────────────────────

def send_newsletter_email(subject, html_body, recipients):
    cfg = EMAIL
    if not all([cfg["from_addr"], cfg["smtp_user"], cfg["smtp_password"]]):
        print("  [WARN] Email not configured — set SMTP variables in .env")
        return False

    if not recipients:
        print("  [WARN] No active subscribers to send to")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{NEWSLETTER_NAME} <{cfg['from_addr']}>"
    msg["To"] = cfg["from_addr"]
    msg["Subject"] = subject

    plain = f"View this issue online: https://yourusername.github.io/ai-newsletter/"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    all_recipients = [cfg["from_addr"]] + recipients

    try:
        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=15) as server:
            server.starttls()
            server.login(cfg["smtp_user"], cfg["smtp_password"])
            server.sendmail(cfg["from_addr"], all_recipients, msg.as_string())
        print(f"  Email sent to {len(recipients)} subscriber(s)")
        return True
    except Exception as e:
        print(f"  [WARN] SMTP failed: {e}")
        return False


# ── Main publish flow ────────────────────────────────────────────────────────

def publish(target_date=None, email_only=False, site_only=False, dry_run=False):
    if target_date is None:
        target_date = date.today().isoformat()

    draft_file = DRAFTS_DIR / f"{target_date}.md"
    if not draft_file.exists():
        print(f"  [ERROR] No draft for {target_date}")
        print(f"  Run: python3 summarizer.py --date {target_date}")
        sys.exit(1)

    with open(draft_file, "r", encoding="utf-8") as f:
        md_content = f.read()

    print(f"\nThe AI Brief — Publisher — {target_date}")
    print("=" * 50)

    content_html = markdown_to_html(md_content)

    if dry_run:
        print("\n(Dry run — previewing HTML)\n")
        preview_file = DRAFTS_DIR / f"{target_date}-preview.html"
        with open(preview_file, "w", encoding="utf-8") as f:
            f.write(build_email_html(content_html, target_date))
        print(f"  Preview saved to {preview_file}")
        return

    if not email_only:
        print("\n[Site]")
        issue_file = ISSUES_DIR / f"{target_date}.html"
        with open(issue_file, "w", encoding="utf-8") as f:
            f.write(build_site_page(content_html, target_date, md_content=md_content))
        print(f"  Created {issue_file}")

        timeline_html = markdown_to_timeline_html(md_content, target_date)
        update_index_page(timeline_html, target_date, md_content=md_content)
        update_archive_page()

    if not site_only:
        print("\n[Email]")
        subject = generate_subject_line(target_date, md_content)
        print(f"  Subject: {subject}")
        email_html = build_email_html(content_html, target_date)
        recipients = get_active_emails()
        send_newsletter_email(subject, email_html, recipients)

    print("\nDone!")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    target_date = None
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            target_date = sys.argv[idx + 1]

    dry_run = "--dry-run" in sys.argv
    email_only = "--email-only" in sys.argv
    site_only = "--site-only" in sys.argv

    publish(target_date, email_only=email_only, site_only=site_only, dry_run=dry_run)


if __name__ == "__main__":
    main()
