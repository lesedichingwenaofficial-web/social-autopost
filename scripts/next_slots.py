#!/usr/bin/env python3
"""Print the next free daily posting slots for an account (SAST), ready for new_post.py --at.

    python3 scripts/next_slots.py parentsgodlywarehouse 5      # next 5 free slots

Daily slots live in SLOTS below; "00:00" belongs to the day before (it's the 5th post of
that day). Extras the user asks for at other times don't use up a slot.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SAST = timezone(timedelta(hours=2))
SLOTS = {"parentsgodlywarehouse": ["17:00", "18:00", "20:00", "22:00", "00:00"]}
POSTS = Path(__file__).resolve().parent.parent / "posts"


def taken(account):
    out = set()
    for f in POSTS.glob("*/post.json"):
        p = json.loads(f.read_text())
        if p.get("account") == account and p.get("status") != "cancelled":
            out.add(datetime.fromisoformat(p["publish_at"]).astimezone(SAST).strftime("%Y-%m-%d %H:%M"))
    return out


def main():
    account = sys.argv[1] if len(sys.argv) > 1 else "parentsgodlywarehouse"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    slots, used = SLOTS[account], taken(account)
    now = datetime.now(SAST) + timedelta(minutes=5)
    day = now.date()
    found = []
    while len(found) < n:
        for hm in slots:
            h, m = map(int, hm.split(":"))
            when = datetime(day.year, day.month, day.day, h, m, tzinfo=SAST)
            if hm == "00:00":
                when += timedelta(days=1)
            key = when.strftime("%Y-%m-%d %H:%M")
            if when > now and key not in used and len(found) < n:
                found.append(key)
        day += timedelta(days=1)
    print("\n".join(found))


if __name__ == "__main__":
    main()
