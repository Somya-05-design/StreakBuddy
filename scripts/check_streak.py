#!/usr/bin/env python3
"""
GitHub Streak Guard
--------------------
Checks whether today's (UTC) GitHub contribution graph day already has
a commit/contribution. If not, sends a push notification via ntfy.sh
reminding you before the streak resets at 00:00 UTC (5:30 AM IST).

Fully stateless: streak length is recomputed fresh from the last 365
days of contribution data on every run. Nothing is stored anywhere.
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import requests

GH_USERNAME = os.environ.get("GH_USERNAME", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
CHECK_STAGE = os.environ.get("CHECK_STAGE", "soft")

print(f"DEBUG: GH_USERNAME='{GH_USERNAME}' (len={len(GH_USERNAME)})")
print(f"DEBUG: GH_TOKEN set: {bool(GH_TOKEN)}")
print(f"DEBUG: NTFY_TOPIC='{NTFY_TOPIC}' (len={len(NTFY_TOPIC)})")
print(f"DEBUG: CHECK_STAGE='{CHECK_STAGE}'")

if not GH_USERNAME:
    print("FATAL: GH_USERNAME is empty. Check the 'GH_USERNAME' repository "
          "variable under Settings -> Secrets and variables -> Actions -> Variables tab.")
    sys.exit(1)
if not GH_TOKEN:
    print("FATAL: GH_TOKEN is empty. This should come from the built-in "
          "secrets.GITHUB_TOKEN mapped in the workflow file.")
    sys.exit(1)
if not NTFY_TOPIC:
    print("FATAL: NTFY_TOPIC is empty. Check the 'NTFY_TOPIC' repository secret "
          "under Settings -> Secrets and variables -> Actions -> Secrets tab.")
    sys.exit(1)

GRAPHQL_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""

STAGE_CONFIG = {
    "soft": {
        "title_no_streak": "👋 No commit yet today",
        "title_streak": "👋 {streak}-day streak — no commit yet",
        "priority": "default",
        "tags": "eyes",
    },
    "urgent": {
        "title_no_streak": "⏰ Still no commit today",
        "title_streak": "⏰ {streak}-day streak at risk",
        "priority": "high",
        "tags": "warning",
    },
    "final": {
        "title_no_streak": "🚨 Last chance — commit now",
        "title_streak": "🚨 {streak}-day streak dies in ~{hours}h",
        "priority": "urgent",
        "tags": "rotating_light",
    },
}


def fetch_contribution_days():
    resp = requests.post(
        "https://api.github.com/graphql",
        json={"query": GRAPHQL_QUERY, "variables": {"login": GH_USERNAME}},
        headers={"Authorization": f"bearer {GH_TOKEN}"},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()

    if "errors" in payload:
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")

    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = []
    for week in weeks:
        days.extend(week["contributionDays"])
    days.sort(key=lambda d: d["date"])
    return days


def compute_current_streak(days_by_date, today_str):
    streak = 0
    cursor = datetime.strptime(today_str, "%Y-%m-%d").date() - timedelta(days=1)
    while True:
        key = cursor.isoformat()
        if days_by_date.get(key, 0) > 0:
            streak += 1
            cursor -= timedelta(days=1)
        else:
            break
    return streak


def hours_until_utc_midnight(now_utc):
    tomorrow = (now_utc + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    delta = tomorrow - now_utc
    return round(delta.total_seconds() / 3600, 1)


def send_ntfy(title, message, priority, tags):
    resp = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": title.encode("utf-8"),
            "Priority": priority,
            "Tags": tags,
        },
        timeout=15,
    )
    resp.raise_for_status()


def main():
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.date().isoformat()

    days = fetch_contribution_days()
    days_by_date = {d["date"]: d["contributionCount"] for d in days}

    today_count = days_by_date.get(today_str, 0)

    if today_count > 0:
        title = "✅ Good job — already committed today"
        message = (
            f"You've made {today_count} contribution(s) today. "
            f"Streak is safe for now. Keep it up!"
        )
        send_ntfy(title, message, priority="low", tags="white_check_mark")
        print(f"[{CHECK_STAGE}] Already committed today ({today_count} contributions). Sent congrats notification.")
        return

    streak = compute_current_streak(days_by_date, today_str)
    hours_left = hours_until_utc_midnight(now_utc)

    cfg = STAGE_CONFIG.get(CHECK_STAGE, STAGE_CONFIG["soft"])

    if streak > 0:
        title = cfg["title_streak"].format(streak=streak, hours=hours_left)
        message = (
            f"No commits yet today. Your {streak}-day streak resets at "
            f"00:00 UTC (5:30 AM IST) — about {hours_left}h left. Push something!"
        )
    else:
        title = cfg["title_no_streak"]
        message = (
            f"No commits yet today, and no active streak. "
            f"~{hours_left}h left before the day (UTC) closes out. Start one!"
        )

    send_ntfy(title, message, cfg["priority"], cfg["tags"])
    print(f"[{CHECK_STAGE}] Notification sent: {title}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
