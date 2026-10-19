#!/usr/bin/env python3
"""Refresh every IG_TOKEN_* secret so it never hits its 60-day expiry.

Instagram long-lived tokens can be refreshed once they're 24h old; each refresh
gives another 60 days. The new token is written back to the repo secret with
the gh CLI, authenticated by the GH_PAT secret (fine-grained token with
"Secrets: read and write" on this repo).
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

secrets = json.loads(os.environ.get("SECRETS_JSON") or "{}")
repo = os.environ["GITHUB_REPOSITORY"]
pat = secrets.get("GH_PAT")
failures = 0

names = sorted(k for k in secrets if k.startswith("IG_TOKEN_"))
if not names:
    sys.exit("no IG_TOKEN_* secrets found")
if not pat:
    print("warning: GH_PAT secret missing - can check tokens but not save refreshed ones")

for name in names:
    q = urllib.parse.urlencode({"grant_type": "ig_refresh_token", "access_token": secrets[name]})
    try:
        with urllib.request.urlopen(f"https://graph.instagram.com/refresh_access_token?{q}", timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"{name}: refresh FAILED: HTTP {e.code} {e.read().decode(errors='replace')[:300]}")
        failures += 1
        continue
    days = data.get("expires_in", 0) // 86400
    if pat:
        subprocess.run(["gh", "secret", "set", name, "--repo", repo],
                       input=data["access_token"], text=True, check=True,
                       env={**os.environ, "GH_TOKEN": pat})
        print(f"{name}: refreshed, valid {days} more days")
    else:
        print(f"{name}: valid, but not saved (no GH_PAT)")

if failures:
    sys.exit(f"{failures} token(s) failed to refresh - reconnect those accounts")
