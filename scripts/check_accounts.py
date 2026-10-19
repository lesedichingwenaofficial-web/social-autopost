#!/usr/bin/env python3
"""Check every IG_TOKEN_* secret: prints the account it belongs to. Posts nothing."""
import json
import os
import sys
import urllib.error
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
sys.exit(1 if bad else 0)
