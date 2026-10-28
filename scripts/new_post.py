#!/usr/bin/env python3
"""Create a scheduled post folder from local images/videos.

    python3 scripts/new_post.py --account formulasimple \
        --at "2026-10-20 18:00" --caption-file caption.txt slide1.png slide2.png

Videos: --cover sets a Reel's cover image (or --thumb-offset picks a frame), --audio-name
renames its audio. Music: --music bakes your own audio file into a video; with --reel, image
slides become a 9:16 slideshow Reel with that music (Instagram's music library isn't
available through the API).

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

import media as mediatools
import postcrypt

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TZ = ZoneInfo("Africa/Johannesburg")  # user's local time, even on UTC cloud machines
VIDEO_EXT = {".mp4", ".mov"}


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "post"


def to_jpeg(src, dest, story=False):
    img = Image.open(src)
    ratio = img.width / img.height
    if not story and not 0.8 <= ratio <= 1.91:
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
    p.add_argument("--cover", help="cover image for a single-video Reel")
    p.add_argument("--thumb-offset", type=float, help="seconds into the video to use as the cover frame")
    p.add_argument("--audio-name", help="name shown for the Reel's audio")
    p.add_argument("--music", help="audio file (mp3/m4a/wav) to put under the video")
    p.add_argument("--music-volume", type=float, default=1.0, help="0-1, default 1")
    p.add_argument("--keep-original-audio", action="store_true", help="mix music with the video's own sound")
    p.add_argument("--reel", action="store_true", help="turn the image slides into one slideshow Reel")
    p.add_argument("--story", action="store_true",
                   help="post each file as its own Story (9:16, 1080x1920); caption is not shown")
    p.add_argument("--seconds-per-slide", type=float, default=3.0)
    p.add_argument("--pad-color", default="black", help="background around 4:5 slides in a 9:16 Reel")
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

    sources = list(map(Path, a.media))
    videos = [s for s in sources if s.suffix.lower() in VIDEO_EXT]
    if a.story and (a.reel or a.music or a.cover or a.location_id):
        sys.exit("--story can't be combined with --reel, --music, --cover or --location-id")
    if a.reel and videos:
        sys.exit("--reel builds a Reel from images only")
    if a.music and not videos and not a.reel:
        sys.exit("music needs a video - add --reel to turn the images into a slideshow Reel")

    folder = ROOT / "posts" / f"{when:%Y-%m-%d-%H%M}-{a.account}-{slugify(a.name or caption[:40])}"
    if folder.exists():
        sys.exit(f"{folder} already exists")
    folder.mkdir(parents=True)
    try:
        build(a, folder, sources, videos, when, caption)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def build(a, folder, sources, videos, when, caption):

    names = []
    if a.reel:
        mediatools.slideshow(sources, folder / "01.mp4", a.seconds_per_slide, a.music,
                             a.music_volume, a.pad_color)
        names.append("01.mp4")
    else:
        for i, src in enumerate(sources, 1):
            if src.suffix.lower() in VIDEO_EXT:
                name = f"{i:02d}.mp4"
                if a.music:
                    mediatools.add_music(src, a.music, folder / name, a.music_volume,
                                         a.keep_original_audio)
                else:
                    shutil.copy(src, folder / name)
            else:
                name = f"{i:02d}.jpg"
                to_jpeg(src, folder / name, a.story)
            names.append(name)

    reel_opts = {}
    single_video = len(names) == 1 and names[0].endswith(".mp4")
    if (a.cover or a.audio_name) and not single_video:
        sys.exit("--cover and --audio-name only work on a single-video (Reel) post")
    if a.cover:
        Image.open(a.cover).convert("RGB").save(folder / "cover.jpg", "JPEG", quality=95)
        reel_opts["cover"] = "cover.jpg"
    if a.thumb_offset is not None:
        reel_opts["thumb_offset_ms"] = int(a.thumb_offset * 1000)
    if a.audio_name:
        reel_opts["audio_name"] = a.audio_name
    size_mb = sum(f.stat().st_size for f in folder.iterdir()) / 1e6
    if size_mb > 90:
        sys.exit(f"post is {size_mb:.0f} MB - GitHub rejects files over 100 MB; compress the video")

    post = {
        "account": a.account,
        "publish_at": when.isoformat(timespec="minutes"),
        "caption": caption,
        "media": names,
        **({"location_id": a.location_id} if a.location_id else {}),
        **reel_opts,
        **({"story": True} if a.story else {}),
        "status": "scheduled",
    }
    if not a.no_lock:
        post = postcrypt.lock(folder, post)
    (folder / "post.json").write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")
    print(folder.relative_to(ROOT))


if __name__ == "__main__":
    main()
