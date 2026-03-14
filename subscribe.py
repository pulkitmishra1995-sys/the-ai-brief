#!/usr/bin/env python3
"""
Subscriber management for The AI Brief.

Usage:
    python3 subscribe.py add user@email.com "Name"
    python3 subscribe.py remove user@email.com
    python3 subscribe.py list
"""

import csv
import hashlib
import hmac
import re
import smtplib
import sys
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote

from config import (
    SUBSCRIBERS_CSV, SUBSCRIBER_FIELDS, EMAIL,
    NEWSLETTER_NAME, OXFORD_BLUE, SITE_URL, UNSUBSCRIBE_SECRET,
)


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _validate_email(email):
    """Return True if email looks valid, False otherwise."""
    return bool(_EMAIL_RE.match(email))


def load_subscribers():
    """Load all subscribers from CSV."""
    if not SUBSCRIBERS_CSV.exists():
        return []
    with open(SUBSCRIBERS_CSV, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_subscribers(subscribers):
    """Write subscribers list to CSV."""
    with open(SUBSCRIBERS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUBSCRIBER_FIELDS)
        writer.writeheader()
        writer.writerows(subscribers)


def _generate_token(email):
    """Generate a deterministic HMAC-SHA256 token for the given email."""
    return hmac.new(
        UNSUBSCRIBE_SECRET.encode(),
        email.lower().encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def _get_unsubscribe_url(email):
    """Build the full unsubscribe URL for a subscriber."""
    token = _generate_token(email)
    return f"{SITE_URL}unsubscribe.html?email={quote(email)}&token={token}"


def verify_unsubscribe_token(email, token):
    """Verify that an unsubscribe token is valid for the given email."""
    expected = _generate_token(email)
    return hmac.compare_digest(expected, token)


def send_welcome_email(email, name=""):
    """Send a branded welcome email to a new subscriber.

    Graceful no-op if SMTP is not configured.
    """
    cfg = EMAIL
    if not all([cfg["from_addr"], cfg["smtp_user"], cfg["smtp_password"]]):
        print("  [WARN] SMTP not configured — skipping welcome email")
        return

    unsubscribe_url = _get_unsubscribe_url(email)
    greeting = f"Hi {name}," if name else "Hi there,"

    html_body = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;">
    <div style="background:{OXFORD_BLUE};padding:24px 32px;text-align:center;">
      <h1 style="margin:0;color:#ffffff;font-size:24px;letter-spacing:1px;">Welcome to {NEWSLETTER_NAME}</h1>
    </div>
    <div style="padding:24px 32px;line-height:1.7;color:#333;font-size:15px;">
      <p>{greeting}</p>
      <p>Thanks for subscribing! Here's what you can expect:</p>
      <ul style="padding-left:20px;">
        <li><strong>Top AI stories</strong> — the signal, not the noise</li>
        <li><strong>Funding &amp; deals</strong> — who raised, who acquired</li>
        <li><strong>Podcasts &amp; videos</strong> — worth your commute</li>
        <li><strong>London &amp; Oxford events</strong> — meetups, talks, hackathons</li>
      </ul>
      <p>Delivered daily so you don't have to doom-scroll.</p>
      <p style="margin-top:20px;">
        <a href="{SITE_URL}archive.html" style="color:{OXFORD_BLUE};font-weight:600;">Browse past issues &rarr;</a>
      </p>
    </div>
    <div style="background:#f0f2f5;padding:20px 32px;text-align:center;font-size:13px;color:#666;">
      <p style="margin:0;">
        <a href="{unsubscribe_url}" style="color:#666;">Unsubscribe</a>
        &middot;
        <a href="{SITE_URL}" style="color:#666;">View online</a>
      </p>
    </div>
  </div>
</body>
</html>"""

    plain_body = f"""\
{greeting}

Thanks for subscribing to {NEWSLETTER_NAME}!

Here's what you can expect:
- Top AI stories — the signal, not the noise
- Funding & deals — who raised, who acquired
- Podcasts & videos — worth your commute
- London & Oxford events — meetups, talks, hackathons

Browse past issues: {SITE_URL}archive.html

Unsubscribe: {unsubscribe_url}"""

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{NEWSLETTER_NAME} <{cfg['from_addr']}>"
    msg["To"] = email
    msg["Subject"] = f"Welcome to {NEWSLETTER_NAME}!"
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=15) as server:
            server.starttls()
            server.login(cfg["smtp_user"], cfg["smtp_password"])
            server.sendmail(cfg["from_addr"], [email], msg.as_string())
        print(f"  Welcome email sent to {email}")
    except Exception as e:
        print(f"  [WARN] Failed to send welcome email: {e}")


def add_subscriber(email, name=""):
    """Add a subscriber or re-activate if previously unsubscribed."""
    if not _validate_email(email):
        print(f"  Error: invalid email address: {email}")
        return
    subscribers = load_subscribers()

    for sub in subscribers:
        if sub["email"].lower() == email.lower():
            if sub["status"] == "active":
                print(f"  Already subscribed: {email}")
                return
            sub["status"] = "active"
            sub["name"] = name or sub["name"]
            save_subscribers(subscribers)
            print(f"  Re-activated: {email}")
            send_welcome_email(email, name or sub["name"])
            return

    subscribers.append({
        "email": email,
        "name": name,
        "date_subscribed": date.today().isoformat(),
        "status": "active",
    })
    save_subscribers(subscribers)
    print(f"  Added: {email} ({name})")
    send_welcome_email(email, name)


def remove_subscriber(email):
    """Soft-delete a subscriber by setting status to unsubscribed."""
    subscribers = load_subscribers()
    found = False

    for sub in subscribers:
        if sub["email"].lower() == email.lower():
            if sub["status"] == "unsubscribed":
                print(f"  Already unsubscribed: {email}")
                return
            sub["status"] = "unsubscribed"
            found = True
            break

    if found:
        save_subscribers(subscribers)
        print(f"  Unsubscribed: {email}")
    else:
        print(f"  Not found: {email}")


def list_subscribers():
    """Print all subscribers with their status."""
    subscribers = load_subscribers()
    if not subscribers:
        print("  No subscribers yet.")
        return

    active = [s for s in subscribers if s["status"] == "active"]
    inactive = [s for s in subscribers if s["status"] != "active"]

    print(f"\n  Active subscribers ({len(active)}):")
    for s in active:
        print(f"    {s['email']:<35} {s['name']:<20} {s['date_subscribed']}")

    if inactive:
        print(f"\n  Unsubscribed ({len(inactive)}):")
        for s in inactive:
            print(f"    {s['email']:<35} {s['name']:<20} {s['date_subscribed']}")

    print(f"\n  Total: {len(active)} active, {len(inactive)} unsubscribed")


def get_active_emails():
    """Return list of active subscriber email addresses."""
    subscribers = load_subscribers()
    return [s["email"] for s in subscribers if s["status"] == "active"]


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 subscribe.py add user@email.com \"Name\"")
        print("  python3 subscribe.py remove user@email.com")
        print("  python3 subscribe.py list")
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "add":
        if len(sys.argv) < 3:
            print("  Error: email required")
            sys.exit(1)
        email = sys.argv[2]
        name = sys.argv[3] if len(sys.argv) > 3 else ""
        add_subscriber(email, name)

    elif action == "remove":
        if len(sys.argv) < 3:
            print("  Error: email required")
            sys.exit(1)
        remove_subscriber(sys.argv[2])

    elif action == "list":
        list_subscribers()

    else:
        print(f"  Unknown action: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
