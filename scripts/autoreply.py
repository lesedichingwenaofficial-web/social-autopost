#!/usr/bin/env python3
"""Reply to keyword comments ("PATH") with a public comment reply and a private DM.

Runs from the publish loop every few minutes. Rules live in autoreply.json:
    {
      "parentsgodlywarehouse": {
        "enabled": true,
        "keywords": ["path"],                # whole word, any case: "PATH", "Path please 🙏"
        "replies": ["Sent you a DM 💛", ...], # one is picked at random per comment
        "dm": "Hi! Here are the details ..."  # sent as an Instagram private reply
      }
    }
Comments already answered are recorded (by id only) in autoreply-state.json so nobody
gets the reply twice. Instagram allows one private reply per comment, within 7 days.

Token permissions needed: instagram_business_manage_comments (reply) and
instagram_business_manage_messages (DM).

Env: IG_TOKEN_<ACCOUNT> as for publish.py; DRY_RUN=1 prints instead of replying.
"""
import json
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from publish import GRAPH, ApiError, api, token_for

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "autoreply.json"
STATE = ROOT / "autoreply-state.json"
WINDOW = timedelta(days=7)     # Instagram's limit for private replies
MAX_MEDIA = 15                 # most recent posts checked per account
MAX_TRIES = 3

DRY_RUN = os.environ.get("DRY_RUN") == "1"


def matches(text, keywords):
    return any(re.search(rf"(?<!\w){re.escape(k)}(?!\w)", text or "", re.IGNORECASE) for k in keywords)


def pages(path, **params):
    """Yield items across paginated Graph API results."""
    data = api("GET", path, **params)
    while True:
        yield from data.get("data", [])
        nxt = data.get("paging", {}).get("next")
        if not nxt:
            return
        data = api("GET", nxt)


def handle_account(account, rule, token, state, now):
    me = api("GET", "me", fields="user_id,username", access_token=token)
    ig_id, username = me["user_id"], me.get("username", "")
    done = state.setdefault(account, {})
    sent = 0
    media = api("GET", "me/media", fields="id,timestamp", limit=MAX_MEDIA, access_token=token).get("data", [])
    for m in media:
        if datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")) < now - WINDOW:
            continue
        for c in pages(f"{m['id']}/comments", fields="id,text,username,timestamp", limit=50, access_token=token):
            if c.get("username", "").lower() == username.lower() or not matches(c.get("text"), rule["keywords"]):
                continue
            rec = done.setdefault(c["id"], {})
            if rec.get("reply") and rec.get("dm") or rec.get("tries", 0) >= MAX_TRIES:
                continue
            if datetime.fromisoformat(c["timestamp"].replace("+0000", "+00:00")) < now - WINDOW:
                rec["tries"] = MAX_TRIES  # too old for a private reply; leave it alone
                continue
            print(f"  @{account}: comment {c['id']} matches")
            if DRY_RUN:
                print(f"    [dry run] would reply and DM")
                continue
            try:
                if not rec.get("reply"):
                    api("POST", f"{c['id']}/replies", message=random.choice(rule["replies"]), access_token=token)
                    rec["reply"] = True
                if not rec.get("dm"):
                    api("POST", f"{GRAPH}/{ig_id}/messages", access_token=token,
                        recipient=json.dumps({"comment_id": c["id"]}),
                        message=json.dumps({"text": rule["dm"]}, ensure_ascii=False))
                    rec["dm"] = True
                sent += 1
            except ApiError as e:
                rec["tries"] = rec.get("tries", 0) + 1
                print(f"    FAILED (try {rec['tries']}): {e}")
    return sent


def main():
    rules = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    secrets = {k: v for k, v in os.environ.items() if k.startswith("IG_TOKEN_") and v}
    now = datetime.now(timezone.utc)
    for account, rule in rules.items():
        if not rule.get("enabled"):
            continue
        if "LINK_GOES_HERE" in rule.get("dm", ""):
            print(f"@{account}: autoreply.json still has the LINK_GOES_HERE placeholder, skipping")
            continue
        try:
            token = token_for(account, secrets)
            n = handle_account(account, rule, token, state, now)
            if n:
                print(f"@{account}: answered {n} comment(s)")
        except ApiError as e:
            print(f"@{account}: {e}")
    if not DRY_RUN:
        STATE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    sys.exit(main())
