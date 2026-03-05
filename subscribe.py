#!/usr/bin/env python3
"""
Subscriber management for The AI Brief.

Usage:
    python3 subscribe.py add user@email.com "Name"
    python3 subscribe.py remove user@email.com
    python3 subscribe.py list
"""

import csv
import sys
from datetime import date

from config import SUBSCRIBERS_CSV, SUBSCRIBER_FIELDS


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


def add_subscriber(email, name=""):
    """Add a subscriber or re-activate if previously unsubscribed."""
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
            return

    subscribers.append({
        "email": email,
        "name": name,
        "date_subscribed": date.today().isoformat(),
        "status": "active",
    })
    save_subscribers(subscribers)
    print(f"  Added: {email} ({name})")


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
