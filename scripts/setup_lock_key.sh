#!/usr/bin/env bash
# One-time: create the key pair that locks scheduled posts.
#   public key  -> keys/public.pem (committed; every Claude session uses it to lock posts)
#   private key -> GitHub secret POST_PRIVATE_KEY (only the publisher can unlock), then deleted here
# Running it again makes a NEW pair: posts locked with the old key can no longer be unlocked.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
umask 077
KEY=$(mktemp)
trap 'shred -u "$KEY" 2>/dev/null || rm -f "$KEY"' EXIT
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$KEY" 2>/dev/null
mkdir -p keys
openssl pkey -in "$KEY" -pubout -out keys/public.pem
gh secret set POST_PRIVATE_KEY --repo "$REPO" < "$KEY"
git add keys/public.pem
git commit -qm "Add post lock public key" && git pull -q --rebase && git push -q
echo "Done: keys/public.pem committed, POST_PRIVATE_KEY saved in GitHub, private key deleted locally."
