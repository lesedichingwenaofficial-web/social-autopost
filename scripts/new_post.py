#!/usr/bin/env python3
"""Create a scheduled post folder from local images/videos.

    python3 scripts/new_post.py --account formulasimple \
        --at "2026-10-20 18:00" --caption-file caption.txt slide1.png slide2.png

Images are converted to JPEG (Instagram's API only accepts JPEG) and checked
against Instagram's limits. Times without a timezone are South African time (SAST).
Content is locked (encrypted) by default until the publisher reveals it at posting
time - see postcrypt.py. Needs Pillow (pip install pillow) and the openssl CLI.
"""
import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from PIL import Image

import postcrypt

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TZ = ZoneInfo("Africa/Johannesburg")  # user's local time, even on UTC cloud machines
VIDEO_EXT = {".mp4", ".mov"}


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "post"


def to_jpeg(src, dest):
    img = Image.open(src)
    ratio = img.width / img.height
    if not 0.8 <= ratio <= 1.91:
        print(f"warning: {src.name} is {img.width}x{img.height}; Instagram wants "
              "aspect ratio between 4:5 and 1.91:1 and may reject it")
    if img.width > 1440:
        img = img.resize((1440, round(1440 / ratio)), Image.LANCZOS)
    img.convert("RGB").save(dest, "JPEG", quality=95)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--account", required=True, help="e.g. formulasimple")
    p.add_argument("--at", required=True, help='"YYYY-MM-DD HH:MM" (local time) or ISO with offset')
    cap = p.add_mutually_exclusive_group(required=True)
    cap.add_argument("--caption")
    cap.add_argument("--caption-file")
    p.add_argument("--name", help="folder name hint")
    p.add_argument("--location-id", help="Facebook place Page ID, e.g. 108424279189115 = New York, NY")
    p.add_argument("--no-lock", action="store_true",
                   help="leave images/caption readable in the public repo until posting")
    p.add_argument("media", nargs="+")
    a = p.parse_args()

    if not a.no_lock and not postcrypt.PUBLIC_KEY.exists():
        sys.exit("keys/public.pem missing - run scripts/setup_lock_key.sh once (or pass --no-lock)")
    when = datetime.fromisoformat(a.at.replace(" ", "T"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=DEFAULT_TZ)
    caption = a.caption if a.caption is not None else Path(a.caption_file).read_text().strip()

    hashtags = len(re.findall(r"#\w+", caption))
    if len(caption) > 2200 or hashtags > 30:
        sys.exit(f"caption too long ({len(caption)}/2200 chars, {hashtags}/30 hashtags)")
    if not 1 <= len(a.media) <= 10:
        sys.exit("need 1-10 media files")

    folder = ROOT / "posts" / f"{when:%Y-%m-%d-%H%M}-{a.account}-{slugify(a.name or caption[:40])}"
    if folder.exists():
        sys.exit(f"{folder} already exists")
    folder.mkdir(parents=True)

    names = []
    for i, src in enumerate(map(Path, a.media), 1):
        if src.suffix.lower() in VIDEO_EXT:
            name = f"{i:02d}{src.suffix.lower()}"
            shutil.copy(src, folder / name)
        else:
            name = f"{i:02d}.jpg"
            to_jpeg(src, folder / name)
        names.append(name)

    post = {
        "account": a.account,
        "publish_at": when.isoformat(timespec="minutes"),
        "caption": caption,
        "media": names,
        **({"location_id": a.location_id} if a.location_id else {}),
        "status": "scheduled",
    }
    if not a.no_lock:
        post = postcrypt.lock(folder, post)
    (folder / "post.json").write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")
    print(folder.relative_to(ROOT))


if __name__ == "__main__":
    main()
