#!/usr/bin/env python3
"""Publish every due post in posts/ to Instagram.

Runs inside GitHub Actions on a schedule. Uses only the standard library.

A post lives in posts/<id>/post.json:
    {
      "account": "formulasimple",              # token comes from secret IG_TOKEN_FORMULASIMPLE
      "publish_at": "2026-10-20T18:00:00+02:00",
      "caption": "...",
      "media": ["01.jpg", "02.jpg"],           # 1 file = single post, 2-10 = carousel, .mp4 = reel/video
      "location_id": "108424279189115",        # optional: Facebook place Page ID (New York, NY)
      "status": "scheduled"                    # scheduled -> posted | failed
    }
Locked posts (the default, see postcrypt.py) hold only account/publish_at/status in
post.json; caption and media are encrypted until this script reveals them - pushes the
decrypted files a minute or two before publishing so Instagram can download them.
Posts due within LOOKAHEAD are waited for, so they go out on the minute.

Env:
    IG_TOKEN_<ACCOUNT>  one env var per account, mapped from repo secrets in the workflow
    MEDIA_BASE_URL public base URL that serves the repo files at this commit
    POST_PRIVATE_KEY    private key that unlocks locked posts
    GITHUB_REPOSITORY   owner/repo, for raw URLs of freshly revealed media
    DRY_RUN=1      print what would happen, call nothing
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import postcrypt

GRAPH = "https://graph.instagram.com/v23.0"
ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
MAX_ATTEMPTS = 3
LOOKAHEAD = timedelta(minutes=6)   # posts due this soon are waited for, so they go out on the minute
RETRY_AFTER = timedelta(minutes=10)  # spacing between attempts at a failing post
VIDEO_EXT = {".mp4", ".mov"}

DRY_RUN = os.environ.get("DRY_RUN") == "1"


class ApiError(Exception):
    pass


def api(method, path, **params):
    url = path if path.startswith("http") else f"{GRAPH}/{path}"
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        # paging "next" URLs already carry their own query string
        req = urllib.request.Request(f"{url}?{data.decode()}" if params else url)
    else:
        req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            msg = json.loads(body)["error"]["message"]
        except Exception:
            msg = body[:500]
        where = path.split("?")[0]  # never echo query strings (they can hold the access token)
        raise ApiError(f"{method} {where}: HTTP {e.code}: {msg}") from None


def token_for(account, secrets):
    name = "IG_TOKEN_" + account.upper().replace(".", "_").replace("-", "_")
    token = secrets.get(name)
    if not token:
        raise ApiError(f"missing GitHub secret {name} for account '{account}'")
    return token


def wait_until_ready(container_id, token, timeout=600):
    """Videos need processing time; images are usually ready immediately."""
    deadline = time.time() + timeout
    while True:
        status = api("GET", container_id, fields="status_code,status", access_token=token)
        code = status.get("status_code")
        if code in (None, "FINISHED", "PUBLISHED"):
            return
        if code in ("ERROR", "EXPIRED"):
            raise ApiError(f"container {container_id} {code}: {status.get('status')}")
        if time.time() > deadline:
            raise ApiError(f"container {container_id} still {code} after {timeout}s")
        time.sleep(10)


def create_item(ig_id, token, url, carousel_item=False, caption=None, location_id=None, **reel):
    params = {"access_token": token, **reel}
    if Path(url).suffix.lower() in VIDEO_EXT:
        params["video_url"] = url
        params["media_type"] = "VIDEO" if carousel_item else "REELS"
    else:
        params["image_url"] = url
    if carousel_item:
        params["is_carousel_item"] = "true"
    if caption:
        params["caption"] = caption
    if location_id:
        params["location_id"] = location_id
    return api("POST", f"{ig_id}/media", **params)["id"]


def publish(post, post_dir, secrets, base_url):
    token = token_for(post["account"], secrets)
    media = post["media"]
    if not 1 <= len(media) <= 10:
        raise ApiError(f"need 1-10 media files, got {len(media)}")
    rel = post_dir.relative_to(ROOT).as_posix()
    urls = [f"{base_url}/{rel}/{urllib.parse.quote(m)}" for m in media]
    caption = post.get("caption", "")
    location = {"location_id": post["location_id"]} if post.get("location_id") else {}
    reel = {}
    if post.get("cover"):
        reel["cover_url"] = f"{base_url}/{rel}/{urllib.parse.quote(post['cover'])}"
    if post.get("thumb_offset_ms") is not None:
        reel["thumb_offset"] = str(post["thumb_offset_ms"])
    if post.get("audio_name"):
        reel["audio_name"] = post["audio_name"]

    if DRY_RUN:
        print(f"  [dry run] would publish {len(urls)} file(s) as @{post['account']}:")
        for u in urls:
            print(f"    {u}")
        return "dry-run"

    ig_id = api("GET", "me", fields="user_id,username", access_token=token)["user_id"]

    if len(urls) == 1:
        container = create_item(ig_id, token, urls[0], caption=caption, **location, **reel)
    else:
        children = []
        for u in urls:
            child = create_item(ig_id, token, u, carousel_item=True)
            wait_until_ready(child, token)
            children.append(child)
        container = api("POST", f"{ig_id}/media", media_type="CAROUSEL",
                        children=",".join(children), caption=caption,
                        access_token=token, **location)["id"]
    wait_until_ready(container, token)
    media_id = api("POST", f"{ig_id}/media_publish", creation_id=container,
                   access_token=token)["id"]
    try:
        link = api("GET", media_id, fields="permalink", access_token=token).get("permalink")
    except ApiError:
        link = None
    return link or media_id


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def reveal(post_file, post):
    """Unlock a locked post and push the plain files; returns the raw base URL for that commit."""
    key = os.environ.get("POST_PRIVATE_KEY")
    if not key:
        raise ApiError("post is locked but the POST_PRIVATE_KEY secret is missing")
    full = postcrypt.unlock(post_file.parent, post, key)
    post_file.write_text(json.dumps(full, indent=2, ensure_ascii=False) + "\n")
    git("config", "user.name", "autopost-bot")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("add", "-A", str(post_file.parent))
    git("commit", "-m", f"Reveal {post_file.parent.name} for publishing")
    for attempt in range(3):
        try:
            git("pull", "--rebase", "-q")
            git("push", "-q")
            break
        except subprocess.CalledProcessError:
            if attempt == 2:
                raise
            time.sleep(5)
    base = f"https://raw.githubusercontent.com/{os.environ['GITHUB_REPOSITORY']}/{git('rev-parse', 'HEAD')}"
    first = f"{base}/{post_file.parent.relative_to(ROOT).as_posix()}/{urllib.parse.quote(full['media'][0])}"
    for _ in range(12):  # wait until GitHub serves the new commit
        try:
            urllib.request.urlopen(urllib.request.Request(first, method="HEAD"), timeout=20)
            break
        except urllib.error.URLError:
            time.sleep(5)
    return full, base


def main():
    secrets = {k: v for k, v in os.environ.items() if (k.startswith("IG_TOKEN_") or k == "GH_PAT") and v}
    base_url = os.environ.get("MEDIA_BASE_URL", "").rstrip("/")
    if not base_url and not DRY_RUN:
        sys.exit("MEDIA_BASE_URL is not set")
    now = datetime.now(timezone.utc)
    failures = 0

    due = []
    for post_file in sorted(POSTS.glob("*/post.json")):
        post = json.loads(post_file.read_text())
        if post.get("status") != "scheduled":
            continue
        when = datetime.fromisoformat(post["publish_at"])
        if when.tzinfo is None:
            print(f"{post_file.parent.name}: publish_at has no timezone, skipping")
            failures += 1
            continue
        last = post.get("last_attempt_at")
        if last and datetime.fromisoformat(last) > now - RETRY_AFTER:
            continue
        if when <= now + LOOKAHEAD:
            due.append((when, post_file, post))

    for when, post_file, post in sorted(due, key=lambda d: d[0]):
        wait = (when - datetime.now(timezone.utc)).total_seconds()
        if wait > 0 and not DRY_RUN:
            print(f"{post_file.parent.name}: due {post['publish_at']}, waiting {wait:.0f}s")
            time.sleep(wait)
        print(f"{post_file.parent.name}: due {post['publish_at']}, publishing...")
        try:
            post_base = base_url
            if post.get("locked"):
                if DRY_RUN:
                    print("  [dry run] locked - would unlock, reveal and publish")
                    continue
                post, post_base = reveal(post_file, post)
            result = publish(post, post_file.parent, secrets, post_base)
        except Exception as e:
            post = json.loads(post_file.read_text())  # on-disk state (may be revealed already)
            post["attempts"] = post.get("attempts", 0) + 1
            post["last_error"] = str(e)
            post["last_attempt_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if post["attempts"] >= MAX_ATTEMPTS:
                post["status"] = "failed"
            print(f"  FAILED (attempt {post['attempts']}): {e}")
            failures += 1
        else:
            if DRY_RUN:
                continue
            post["status"] = "posted"
            post["posted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            post["result"] = result
            post.pop("last_error", None)
            post.pop("last_attempt_at", None)
            print(f"  posted: {result}")
        if not DRY_RUN:
            post_file.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")

    if failures:
        sys.exit(f"{failures} post(s) failed - see log above")


if __name__ == "__main__":
    main()
