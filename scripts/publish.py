#!/usr/bin/env python3
"""Publish every due post in posts/ to Instagram.

Runs inside GitHub Actions on a schedule. Uses only the standard library.

A post lives in posts/<id>/post.json:
    {
      "account": "formulasimple",              # token comes from secret IG_TOKEN_FORMULASIMPLE
      "publish_at": "2026-10-20T18:00:00+02:00",
      "caption": "...",
      "media": ["01.jpg", "02.jpg"],           # 1 file = single post, 2-10 = carousel, .mp4 = reel/video
      "status": "scheduled"                    # scheduled -> posted | failed
    }

Env:
    IG_TOKEN_<ACCOUNT>  one env var per account, mapped from repo secrets in the workflow
    MEDIA_BASE_URL public base URL that serves the repo files at this commit
    DRY_RUN=1      print what would happen, call nothing
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

GRAPH = "https://graph.instagram.com/v23.0"
ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
MAX_ATTEMPTS = 3
VIDEO_EXT = {".mp4", ".mov"}

DRY_RUN = os.environ.get("DRY_RUN") == "1"


class ApiError(Exception):
    pass


def api(method, path, **params):
    url = path if path.startswith("http") else f"{GRAPH}/{path}"
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
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
        raise ApiError(f"{method} {path}: HTTP {e.code}: {msg}") from None


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


def create_item(ig_id, token, url, carousel_item=False, caption=None):
    params = {"access_token": token}
    if Path(url).suffix.lower() in VIDEO_EXT:
        params["video_url"] = url
        params["media_type"] = "VIDEO" if carousel_item else "REELS"
    else:
        params["image_url"] = url
    if carousel_item:
        params["is_carousel_item"] = "true"
    if caption:
        params["caption"] = caption
    return api("POST", f"{ig_id}/media", **params)["id"]


def publish(post, post_dir, secrets, base_url):
    token = token_for(post["account"], secrets)
    media = post["media"]
    if not 1 <= len(media) <= 10:
        raise ApiError(f"need 1-10 media files, got {len(media)}")
    rel = post_dir.relative_to(ROOT).as_posix()
    urls = [f"{base_url}/{rel}/{urllib.parse.quote(m)}" for m in media]
    caption = post.get("caption", "")

    if DRY_RUN:
        print(f"  [dry run] would publish {len(urls)} file(s) as @{post['account']}:")
        for u in urls:
            print(f"    {u}")
        return "dry-run"

    ig_id = api("GET", "me", fields="user_id,username", access_token=token)["user_id"]

    if len(urls) == 1:
        container = create_item(ig_id, token, urls[0], caption=caption)
    else:
        children = []
        for u in urls:
            child = create_item(ig_id, token, u, carousel_item=True)
            wait_until_ready(child, token)
            children.append(child)
        container = api("POST", f"{ig_id}/media", media_type="CAROUSEL",
                        children=",".join(children), caption=caption,
                        access_token=token)["id"]
    wait_until_ready(container, token)
    media_id = api("POST", f"{ig_id}/media_publish", creation_id=container,
                   access_token=token)["id"]
    try:
        link = api("GET", media_id, fields="permalink", access_token=token).get("permalink")
    except ApiError:
        link = None
    return link or media_id


def main():
    secrets = {k: v for k, v in os.environ.items() if (k.startswith("IG_TOKEN_") or k == "GH_PAT") and v}
    base_url = os.environ.get("MEDIA_BASE_URL", "").rstrip("/")
    if not base_url and not DRY_RUN:
        sys.exit("MEDIA_BASE_URL is not set")
    now = datetime.now(timezone.utc)
    failures = 0

    for post_file in sorted(POSTS.glob("*/post.json")):
        post = json.loads(post_file.read_text())
        if post.get("status") != "scheduled":
            continue
        due = datetime.fromisoformat(post["publish_at"])
        if due.tzinfo is None:
            print(f"{post_file.parent.name}: publish_at has no timezone, skipping")
            failures += 1
            continue
        if due > now:
            continue

        print(f"{post_file.parent.name}: due {post['publish_at']}, publishing...")
        try:
            result = publish(post, post_file.parent, secrets, base_url)
        except Exception as e:
            post["attempts"] = post.get("attempts", 0) + 1
            post["last_error"] = str(e)
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
            print(f"  posted: {result}")
        if not DRY_RUN:
            post_file.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")

    if failures:
        sys.exit(f"{failures} post(s) failed - see log above")


if __name__ == "__main__":
    main()
