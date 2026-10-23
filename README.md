# Social autopost

Free Instagram scheduling with Claude + GitHub Actions. Claude makes the post;
GitHub publishes it at the scheduled time, even with your laptop off. Many
accounts, no paid tools.

## How it works

```
You + Claude ──► posts/<post>/  (slides + post.json with time & caption)
                     │ git push
                     ▼
GitHub Actions (always-on loop, checks every minute) ──► Instagram API ──► published
                     │
                     └─► writes "posted" + link back into post.json
```

## One-time setup (per Instagram account, steps 1–4)

### 1. Make the account Professional
Instagram app → Settings → *Account type and tools* → *Switch to professional
account* (Creator or Business). Free, and no Facebook Page is needed.

### 2. Create a Meta developer app (only once, shared by all accounts)
1. Go to <https://developers.facebook.com/apps> → **Create app**.
2. Use case: **Manage messaging & content on Instagram**. App type: **Business** if asked.
3. In the app, open **Instagram → API setup with Instagram login**.

### 3. Get the account's access token
1. Under **Generate access tokens**, click **Add account** and log in to the
   Instagram account. Allow the content-publishing permission.
   - If asked, first add the account under **App roles → Roles → Instagram Testers**,
     then accept the invite in Instagram on the web: Settings → *Apps and websites* → *Tester invites*.
2. Click **Generate token** next to the account and copy it. It's valid for 60 days, and
   the weekly refresh workflow keeps renewing it.

### 4. Save the token in GitHub (you do this, so Claude never sees it)
Run this and paste the token when asked (name = account name in capitals):
```bash
gh secret set IG_TOKEN_FORMULASIMPLE --repo OWNER/social-autopost
```

### 5. Let tokens renew themselves (only once)
1. <https://github.com/settings/personal-access-tokens/new> → fine-grained token,
   **Only select repositories → social-autopost**,
   Repository permissions → **Secrets: Read and write**. Pick the longest expiry.
2. ```bash
   gh secret set GH_PAT --repo OWNER/social-autopost
   ```

### 6. Test
GitHub → Actions → **Refresh Instagram tokens** → *Run workflow*. It should
say each token was refreshed. Then ask Claude to make and schedule a post.

## Day to day
Ask Claude: *"Make a 7-slide breakdown of <video> and post it Friday 18:00 on formulasimple."*
Claude shows you the slides and caption first and schedules only after you approve.

- **Post now:** ask Claude to post now. It runs the workflow immediately.
- **Cancel or reschedule:** ask Claude before the scheduled time.
- **If something fails:** GitHub emails you about the failed run, and the error is in that
  post's `post.json` (`last_error`). It retries 3 times before marking it `failed`.

## Good to know
- Timing: GitHub's scheduler can run late at busy times, so a post usually goes out within
  about 15–30 minutes of its time.
- This repo is **public** (Instagram downloads images from a public link), but scheduled posts are
  **locked**: only the account and time are visible until about a minute before posting.
  One-time setup: `scripts/setup_lock_key.sh`. Tokens stay private in GitHub secrets.
- Limits: up to 10 images/videos per post, 100 posts per day per account.
