# Social autopost

Free Instagram scheduler: posts live in `posts/`, a GitHub Actions workflow
(`.github/workflows/publish.yml`, every 5 min) publishes anything due through
the official Instagram API. The laptop does not need to be on.

## Making a post (what the user asks Claude for)

1. Write slides as HTML in `drafts/<slug>/NN.html`, starting from
   `templates/slide.html` (Formula Simple style: cream grid, #ff5106 accent,
   Space Grotesk + Space Mono, 1080x1350). One idea per slide; number them `01/07`.
2. Render: `scripts/render.sh drafts/<slug>/*.html`, then look at every PNG.
3. Show the user the slides and caption. **Do not schedule until the user
   approves the content and gives a time.** Their approval + time is the
   go-ahead to publish at that time.
4. Schedule:
   `python3 scripts/new_post.py --account <acct> --at "YYYY-MM-DD HH:MM" --caption-file <file> drafts/<slug>/*.png`
   (local time is Africa/Johannesburg, SAST +02:00 unless the user says otherwise)
5. `git add posts && git commit -m "Schedule <slug>"`, then get it onto **main** (the publisher only
   reads main): `git pull --rebase origin main && git push origin HEAD:main`. This matters in
   worktree or cloud/web sessions that start on their own branch - a post pushed only to a side
   branch never publishes. Confirm with `git log origin/main -1`.
6. "Post now": schedule with the current time, push to main, then
   `gh workflow run publish.yml` and watch with `gh run watch`. If `gh` isn't available (e.g. a
   cloud session), the scheduled run picks it up within ~5-15 min.
7. After it posts, `git pull` and report the Instagram link from `result` in post.json.

Posts are **locked** (encrypted) by default: the public repo only shows account + time until the
publisher reveals the images/caption ~1 minute before posting (scripts/postcrypt.py). Sessions can
lock but cannot unlock, so:
- Reschedule: edit `publish_at` in post.json, push to main.
- Cancel: delete the post folder (or set `"status": "cancelled"`), push to main.
- Change caption/images: delete the post and create it again (keep drafts until it has posted).
Runs check every 5 min and wait for anything due in the next 6 min, so posts go out on the minute
when GitHub runs on time.
Check results: `status` / `result` / `last_error` in each `post.json` (the workflow commits them back) — `git pull` first.

## Accounts (`--account` value -> Instagram)
- `formulasimple` -> @formulasimple.co (style: templates/slide.html)
- `cheekyfoundlamb` -> @cheekyfoundlamb (style: not yet defined - ask the user). Target audience is the
  US: always add `--location-id 108424279189115` (New York, NY) to every post.
- `parentsgodlywarehouse` -> @parentsgodlywarehouse (style: not yet defined - ask the user)
- `parentsdispatchedinfo` -> @parentsdispatchedinfo (style: not yet defined - ask the user)
Each account has its own style; never reuse Formula Simple's look for the others.

## Setup in a fresh environment
`pip install pillow` if `python3 -c 'import PIL'` fails. Slide rendering needs Chrome/Chromium
(scripts/render.sh); if none is available, ask the user for finished slide images instead.

## Rules
- Accounts: secret `IG_TOKEN_<ACCOUNT>` per account (e.g. `IG_TOKEN_FORMULASIMPLE`).
  Never ask for, print, or handle token values; the user sets secrets themselves.
  New account: after the user sets its secret, add an `IG_TOKEN_<ACCOUNT>: ${{ secrets.IG_TOKEN_<ACCOUNT> }}`
  line to the env block in publish.yml, refresh-tokens.yml and check-accounts.yml, push, then run
  `gh workflow run check-accounts.yml`. Never pass `toJSON(secrets)` - GitHub flags it as malicious.
- Limits: 1-10 media per post, JPEG images (new_post.py converts), aspect
  4:5 to 1.91:1, caption <= 2200 chars and <= 30 hashtags, 100 posts/day/account.
- The repo is public (Instagram must fetch images by URL), so scheduled
  account names and times are visible; locked content is not. Don't use --no-lock unless asked.
- Location: `--location-id <Facebook place Page ID>` (not an Instagram location id; no country-level
  US page exists). Known: New York, NY = 108424279189115. Verify others at facebook.com/<id>.
- Video: .mp4/.mov post as a Reel (single) or carousel items. Reel options: `--cover img`,
  `--thumb-offset SECONDS`, `--audio-name "..."` (single-video posts only). Keep a post under ~90 MB.
- Music: Instagram's music library is NOT available via the API. Instead bake an audio file the user
  supplies (and has rights to) into the video: `--music song.mp3 [--music-volume 0.4]
  [--keep-original-audio]`. For image slides with music use `--reel --music song.mp3
  [--seconds-per-slide 3] [--pad-color "#f0ebe2"]` - this posts a 9:16 slideshow Reel, not a
  swipeable carousel. Needs ffmpeg (or `pip install imageio-ffmpeg`).
- Test without posting: `DRY_RUN=1 python3 scripts/publish.py`
