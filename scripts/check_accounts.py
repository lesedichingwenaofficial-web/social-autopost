#!/usr/bin/env python3
"""Check every IG_TOKEN_* secret: prints the account it belongs to. Posts nothing."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

secrets = {k: v for k, v in os.environ.items() if (k.startswith("IG_TOKEN_") or k == "GH_PAT") and v}
names = sorted(k for k in secrets if k.startswith("IG_TOKEN_"))
if not names:
    sys.exit("no IG_TOKEN_* secrets found")
bad = 0
for name in names:
    url = "https://graph.instagram.com/v23.0/me?fields=user_id,username,account_type&access_token=" + secrets[name]
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            me = json.load(r)
        print(f"{name}: OK -> @{me.get('username')} ({me.get('account_type')})")
    except urllib.error.HTTPError as e:
        print(f"{name}: FAILED HTTP {e.code} {e.read().decode(errors='replace')[:300]}")
        bad += 1

# Accounts with auto-reply rules also need comment + message access (read-only checks).
rules_file = os.path.join(os.path.dirname(__file__), "..", "autoreply.json")
rules = json.load(open(rules_file)) if os.path.exists(rules_file) else {}
base = "https://graph.instagram.com/v23.0/"
for account in rules:
    name = "IG_TOKEN_" + account.upper().replace(".", "_").replace("-", "_")
    tok = secrets.get(name)
    if not tok:
        continue
    def get(path, **q):
        q["access_token"] = tok
        with urllib.request.urlopen(base + path + "?" + urllib.parse.urlencode(q), timeout=30) as r:
            return json.load(r)
    checks = [("comments (instagram_business_manage_comments)",
               lambda: get(get("me/media", fields="id", limit=1)["data"][0]["id"] + "/comments", limit=1)),
              ("messages (instagram_business_manage_messages + 'Allow access to messages')",
               lambda: get("me/conversations", platform="instagram", limit=1))]
    for label, fn in checks:
        try:
            fn()
            print(f"{name}: {label}: OK")
        except urllib.error.HTTPError as e:
            print(f"{name}: {label}: FAILED HTTP {e.code} {e.read().decode(errors='replace')[:300]}")
            bad += 1
        except Exception as e:
            print(f"{name}: {label}: FAILED {e}")
            bad += 1
sys.exit(1 if bad else 0)
