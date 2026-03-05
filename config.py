#!/usr/bin/env python3
"""
Configuration for The AI Brief — daily AI newsletter.
All settings, feed URLs, schemas, and paths in one place.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DRAFTS_DIR = BASE_DIR / "drafts"
SITE_DIR = BASE_DIR / "site"
SUBSCRIBERS_CSV = DATA_DIR / "subscribers.csv"
SEEN_ARTICLES_FILE = DATA_DIR / "seen_articles.json"
COLLECTED_DIR = DATA_DIR / "collected"
ISSUES_DIR = SITE_DIR / "issues"

# Ensure directories exist
for d in [DATA_DIR, DRAFTS_DIR, SITE_DIR, COLLECTED_DIR, ISSUES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Subscriber schema ────────────────────────────────────────────────────────

SUBSCRIBER_FIELDS = ["email", "name", "date_subscribed", "status"]

# ── RSS feeds ────────────────────────────────────────────────────────────────

RSS_FEEDS = {
    "The Batch (deeplearning.ai)": {
        "url": "https://www.deeplearning.ai/blog/feed/",
        "type": "rss",
    },
    "Import AI": {
        "url": "https://importai.substack.com/feed",
        "type": "rss",
    },
    "TechCrunch AI": {
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "type": "rss",
    },
    "The Verge AI": {
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "type": "rss",
    },
    "MIT Technology Review AI": {
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
        "type": "rss",
    },
    "Ars Technica AI": {
        "url": "https://feeds.arstechnica.com/arstechnica/features",
        "type": "rss",
    },
    "smol.ai": {
        "url": "https://buttondown.com/ainews/rss",
        "type": "rss",
    },
    "Ben's Bites": {
        "url": "https://www.bensbites.com/feed",
        "type": "rss",
    },
    "The Neuron": {
        "url": "https://www.theneurondaily.com/feed",
        "type": "rss",
    },
    "TLDR AI": {
        "url": "https://tldr.tech/ai/rss.xml",
        "type": "rss",
    },
    "Crunchbase AI Funding": {
        "url": "https://news.crunchbase.com/feed/",
        "type": "rss",
    },
    "TechCrunch Venture": {
        "url": "https://techcrunch.com/category/venture/feed/",
        "type": "rss",
    },
}

# ── Podcast feeds ────────────────────────────────────────────────────────────

PODCAST_FEEDS = {
    "Lex Fridman Podcast": {
        "url": "https://lexfridman.com/feed/podcast/",
        "max_episodes": 2,
    },
    "No Priors": {
        "url": "https://feeds.megaphone.fm/nopriors",
        "max_episodes": 2,
    },
    "Latent Space": {
        "url": "https://api.substack.com/feed/podcast/1084089/s/80390.rss",
        "max_episodes": 2,
    },
    "All-In Podcast": {
        "url": "https://allinchamathjason.libsyn.com/rss",
        "max_episodes": 2,
    },
    "The AI Podcast (NVIDIA)": {
        "url": "https://feeds.soundcloud.com/users/soundcloud:users:264034133/sounds.rss",
        "max_episodes": 2,
    },
    "Hard Fork (NYT)": {
        "url": "https://feeds.simplecast.com/l2i9YnTd",
        "max_episodes": 2,
    },
    "Practical AI": {
        "url": "https://changelog.com/practicalai/feed",
        "max_episodes": 2,
    },
    "Acquired": {
        "url": "https://feeds.transistor.fm/acq2",
        "max_episodes": 2,
    },
    "20VC with Harry Stebbings": {
        "url": "https://thetwentyminutevc.libsyn.com/rss",
        "max_episodes": 2,
    },
}

# ── YouTube channels (via RSS) ──────────────────────────────────────────────

YOUTUBE_CHANNELS = {
    "Two Minute Papers": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCbfYPyITQ-7l4upoX8nvctg",
        "max_videos": 2,
    },
    "AI Explained": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCNJ1Ymd5yFuUPtn21xtRbbw",
        "max_videos": 2,
    },
    "Fireship": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCsBjURrPoezykLs9EqgamOA",
        "max_videos": 2,
    },
    "Andrej Karpathy": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCXUPKJO5MZQN11PqgIvyuvQ",
        "max_videos": 2,
    },
    "Yannic Kilcher": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCZHmQk67mSJgfCCTn7xBfew",
        "max_videos": 2,
    },
    "Matt Wolfe": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCJIfeSCssxSC_Dhc5s7woww",
        "max_videos": 2,
    },
    "TheAIGRID": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCbY9xX3_jW5c2fjlZVBI4cg",
        "max_videos": 2,
    },
    "AssemblyAI": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCtatfZMf-8EkIwASXM4ts0A",
        "max_videos": 2,
    },
}

# ── Events config ────────────────────────────────────────────────────────────

EVENTS_CONFIG = {
    "locations": ["London", "Oxford"],
    "eventbrite_urls": [
        "https://www.eventbrite.co.uk/d/{location}/ai-artificial-intelligence/?page=1",
        "https://www.eventbrite.co.uk/d/{location}/startup-technology/?page=1",
    ],
    # Luma discover pages — parsed via __NEXT_DATA__ JSON, not HTML scraping
    "luma_discover_urls": [
        "https://lu.ma/discover?near={location}&tag=ai",
        "https://lu.ma/discover?near={location}&tag=tech",
        "https://lu.ma/discover?near={location}&tag=startups",
    ],
}

EVENTS_KEYWORDS_INCLUDE = [
    "artificial intelligence", "machine learning", "AI", "LLM",
    "deep learning", "generative AI", "GPT", "foundation model", "AI safety",
    "computer vision", "NLP", "robotics", "neural network", "data science",
    "AI startup", "AI ethics",
    "startup", "venture capital", "VC", "founder", "fundraising",
    "pitch", "tech", "fintech", "SaaS", "Series A", "seed round",
    "accelerator", "incubator",
]

EVENTS_KEYWORDS_EXCLUDE = [
    "course", "certification", "bootcamp", "diploma",
    "training program", "accredited", "CPD", "beginner workshop",
]

EVENTS_SPEAKER_SIGNALS = [
    "DeepMind", "OpenAI", "Anthropic", "Google AI", "Meta AI",
    "Oxford", "Cambridge", "Imperial", "professor", "keynote", "fireside",
    "panel", "summit", "conference", "hackathon", "demo day",
    "Y Combinator", "Sequoia", "a16z", "Index Ventures", "Seedcamp",
    "Entrepreneur First", "TechCrunch", "Web Summit",
]

# ── Claude API ───────────────────────────────────────────────────────────────

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
CLAUDE_MAX_TOKENS = 4096

# ── Email / SMTP ─────────────────────────────────────────────────────────────

EMAIL = {
    "from_addr": os.getenv("NEWSLETTER_FROM", ""),
    "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
    "smtp_port": int(os.getenv("SMTP_PORT", "587")),
    "smtp_user": os.getenv("SMTP_USER", ""),
    "smtp_password": os.getenv("SMTP_PASSWORD", ""),
}

# ── Formspree ────────────────────────────────────────────────────────────────

FORMSPREE_ENDPOINT = os.getenv("FORMSPREE_ENDPOINT", "")

# ── Branding ─────────────────────────────────────────────────────────────────

NEWSLETTER_NAME = "The AI Brief"
OXFORD_BLUE = "#002147"

# ── Scraper settings ─────────────────────────────────────────────────────────

REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
USER_AGENT = "TheAIBrief/1.0 (+https://github.com/pulkit)"
