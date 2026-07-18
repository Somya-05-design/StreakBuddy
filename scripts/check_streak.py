#!/usr/bin/env python3
"""
GitHub Streak Guard
--------------------
Checks whether today's (UTC) GitHub contribution graph day already has
a commit/contribution, and sends a Zomato-style playful push via
ntfy.sh at each of 4 checkpoints through the day.

Fully stateless: streak length is recomputed fresh from the last 365
days of contribution data on every run. Nothing is stored anywhere.
"""

import os
import sys
import random
from datetime import datetime, timezone, timedelta

import requests

GITHUB_USERNAME = os.environ.get("GH_USERNAME", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
CHECK_STAGE = os.environ.get("CHECK_STAGE", "stage1")

print(f"DEBUG: GH_USERNAME='{GITHUB_USERNAME}' (len={len(GITHUB_USERNAME)})")
print(f"DEBUG: GH_TOKEN set: {bool(GH_TOKEN)}")
print(f"DEBUG: NTFY_TOPIC='{'*' * len(NTFY_TOPIC)}' (len={len(NTFY_TOPIC)})")
print(f"DEBUG: CHECK_STAGE='{CHECK_STAGE}'")

if not GITHUB_USERNAME:
    print("FATAL: GH_USERNAME is empty. Check the 'GH_USERNAME' repository "
          "variable in Settings -> Secrets and variables -> Actions -> Variables tab.")
    sys.exit(1)
if not GH_TOKEN:
    print("FATAL: GH_TOKEN is empty.")
    sys.exit(1)
if not NTFY_TOPIC:
    print("FATAL: NTFY_TOPIC is empty. Check the 'NTFY_TOPIC' repository secret.")
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

# ---------------------------------------------------------------------------
# Message bank — Zomato-style playful, encouraging, a little cheeky.
# Each stage has its own personality: casual -> nudgy -> concerned -> urgent.
# Multiple options per slot so it doesn't feel like the same robot every day.
# ---------------------------------------------------------------------------

MESSAGES = {
    "stage1": {  # 2 PM IST - start of day energy
        "committed": {
            "titles": [
                "😎 Already {count}x today?!",
                "🐦 Look at this early bird",
            ],
            "bodies": [
                "You've committed {count} time(s) before lunch even settled. {streak}-day streak locked in. Show-off. 🏆",
                "{count} commit(s) down already. The repo is fed, watered, and happy. 🌱",
            ],
        },
        "not_committed": {
            "titles": [
                "☀️ Rise and grind, dev",
                "👀 GitHub's looking a bit empty",
            ],
            "bodies": [
                "It's 2 PM and your repo's emptier than a Monday standup. Kick off the day with one commit!",
                "Your {streak}-day streak is watching you from the couch, waiting. Give it something to do. 💻",
            ],
        },
        "priority": "default",
        "tags": "sunny",
    },
    "stage2": {  # 5 PM IST - afternoon check-in
        "committed": {
            "titles": [
                "💪 Still going strong",
                "🚂 Streak train, chugging along",
            ],
            "bodies": [
                "{count} commit(s) and counting. Keep this train rolling — next stop, tomorrow. 🚂",
                "5 PM and you're already sorted for today. Casual flex. 😌 {streak}-day streak intact.",
            ],
        },
        "not_committed": {
            "titles": [
                "🫤 5 PM and... nothing?",
                "⏳ The repo is getting impatient",
            ],
            "bodies": [
                "Even your coffee break had more action than your GitHub today. Time to commit something!",
                "Your {streak}-day streak just refreshed the page for the 5th time, hoping. Don't ghost it.",
            ],
        },
        "priority": "default",
        "tags": "coffee",
    },
    "stage3": {  # 8 PM IST - evening, getting real
        "committed": {
            "titles": [
                "🎉 Today's basically a wrap",
                "✅ Streak: safely tucked in",
            ],
            "bodies": [
                "{count} commit(s) in the bag. {streak}-day streak sleeping peacefully tonight. 😴",
                "You showed up today. That's the whole game. See you tomorrow, champ. 🏅",
            ],
        },
        "not_committed": {
            "titles": [
                "😰 Tick tock, it's 8 PM",
                "🚧 Streak under construction (still)",
            ],
            "bodies": [
                "Your {streak}-day streak is starting to sweat. A one-line commit still counts — don't let today be the day.",
                "The day's winding down and GitHub's still quiet. Even a typo fix keeps the streak alive. 😅",
            ],
        },
        "priority": "high",
        "tags": "warning",
    },
    "stage4": {  # 10 PM IST - last real nudge before the late-night grace window
        "committed": {
            "titles": [
                "🏆 Day secured. Go rest.",
                "🌙 All good here, night owl",
            ],
            "bodies": [
                "{count} commit(s) done, {streak}-day streak safe. Close the laptop, you've earned it. 🌙",
                "Nothing left to do here except sleep well. Streak's not going anywhere tonight.",
            ],
        },
        "not_committed": {
            "titles": [
                "🚨 Last real call tonight",
                "⚠️ Streak on thin ice",
            ],
            "bodies": [
                "It's 10 PM and still nothing. You've technically got till 5:30 AM, but don't push your luck. One commit, that's it.",
                "Your {streak}-day streak is one commit away from staying alive. Don't let it flatline over something small.",
            ],
        },
        "priority": "urgent",
        "tags": "rotating_light",
    },
}


def fetch_contribution_days():
    resp = requests.post(
        "https://api.github.com/graphql",
        json={"query": GRAPHQL_QUERY, "variables": {"login": GITHUB_USERNAME}},
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


def compute_streak_before_today(days_by_date, today_str):
    """Walk backwards from yesterday counting consecutive contributed days."""
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

    streak_before_today = compute_streak_before_today(days_by_date, today_str)

    stage_cfg = MESSAGES.get(CHECK_STAGE, MESSAGES["stage1"])
    branch = "committed" if today_count > 0 else "not_committed"
    slot = stage_cfg[branch]

    title_template = random.choice(slot["titles"])
    body_template = random.choice(slot["bodies"])

    effective_streak = streak_before_today + 1 if today_count > 0 else streak_before_today

    title = title_template.format(count=today_count, streak=effective_streak)
    message = body_template.format(count=today_count, streak=effective_streak)

    send_ntfy(title, message, stage_cfg["priority"], stage_cfg["tags"])
    print(f"[{CHECK_STAGE}/{branch}] Notification sent: {title}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
