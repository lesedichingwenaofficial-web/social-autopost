# Social autopost

Free Instagram scheduler: posts live in `posts/`, a GitHub Actions workflow
(`.github/workflows/publish.yml`, every 15 min) publishes anything due through
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
5. `git add posts && git commit -m "Schedule <slug>" && git push`
6. "Post now": schedule with the current time, push, then
   `gh workflow run publish.yml` and watch with `gh run watch`.

To cancel or reschedule: edit or delete the post folder (or set `"status": "cancelled"`) and push before its time.
Check results: `status` / `result` / `last_error` in each `post.json` (the workflow commits them back) — `git pull` first.

## Accounts (`--account` value -> Instagram)
- `formulasimple` -> @formulasimple.co (style: templates/slide.html)
- `cheekyfoundlamb` -> @cheekyfoundlamb (style: not yet defined - ask the user)
- `parentsgodlywarehouse` -> @parentsgodlywarehouse (style: not yet defined - ask the user)
- `parentsdispatchedinfo` -> @parentsdispatchedinfo (style: not yet defined - ask the user)
Each account has its own style; never reuse Formula Simple's look for the others.

## Rules
- Accounts: secret `IG_TOKEN_<ACCOUNT>` per account (e.g. `IG_TOKEN_FORMULASIMPLE`).
  Never ask for, print, or handle token values; the user sets secrets themselves.
  New account: after the user sets its secret, add an `IG_TOKEN_<ACCOUNT>: ${{ secrets.IG_TOKEN_<ACCOUNT> }}`
  line to the env block in publish.yml, refresh-tokens.yml and check-accounts.yml, push, then run
  `gh workflow run check-accounts.yml`. Never pass `toJSON(secrets)` - GitHub flags it as malicious.
- Limits: 1-10 media per post, JPEG images (new_post.py converts), aspect
  4:5 to 1.91:1, caption <= 2200 chars and <= 30 hashtags, 100 posts/day/account.
- The repo is public (Instagram must fetch images by URL), so scheduled
  captions/images are visible before they post. Don't put anything private here.
- Location: `--location-id <Facebook place Page ID>` (not an Instagram location id; no country-level
  US page exists). Known: New York, NY = 108424279189115. Verify others at facebook.com/<id>.
- Music: the API cannot add Instagram library music to posts.
- Test without posting: `DRY_RUN=1 python3 scripts/publish.py`
