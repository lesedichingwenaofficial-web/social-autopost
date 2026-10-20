"""Lock a scheduled post so its images and caption aren't public before posting time.

The repo is public (Instagram must download media from a public URL), so a scheduled
post's content is encrypted until the publisher reveals it moments before publishing.

    lock:   anyone with keys/public.pem (every Claude session) can encrypt
    unlock: only the publish workflow, with the POST_PRIVATE_KEY secret

Format, inside posts/<id>/:
    content.enc   AES-256 encrypted tar.gz of content.json + the media files
    key.enc       the random AES key, encrypted with keys/public.pem (RSA-OAEP)
Uses the openssl CLI so nothing needs installing.
"""
import io
import json
import os
import secrets
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_KEY = ROOT / "keys" / "public.pem"
CONTENT_FIELDS = ("caption", "media", "location_id", "cover", "thumb_offset_ms", "audio_name")


def files_of(post):
    return list(post["media"]) + ([post["cover"]] if post.get("cover") else [])


def _openssl(*args, data=None):
    return subprocess.run(["openssl", *args], input=data, capture_output=True, check=True).stdout


def lock(folder, post):
    """Encrypt the post's content + media; returns the public post.json dict."""
    folder = Path(folder)
    content = {k: post[k] for k in CONTENT_FIELDS if k in post}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        blob = json.dumps(content, ensure_ascii=False).encode()
        info = tarfile.TarInfo("content.json")
        info.size = len(blob)
        tar.addfile(info, io.BytesIO(blob))
        for name in files_of(post):
            tar.add(folder / name, arcname=name)
    password = secrets.token_hex(32).encode()
    with tempfile.NamedTemporaryFile() as pw:
        pw.write(password)
        pw.flush()
        (folder / "content.enc").write_bytes(_openssl(
            "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-pass", f"file:{pw.name}", data=buf.getvalue()))
    (folder / "key.enc").write_bytes(_openssl(
        "pkeyutl", "-encrypt", "-pubin", "-inkey", str(PUBLIC_KEY),
        "-pkeyopt", "rsa_padding_mode:oaep", data=password))
    for name in files_of(post):
        (folder / name).unlink()
    public = {k: v for k, v in post.items() if k not in CONTENT_FIELDS}
    public["locked"] = True
    return public


def unlock(folder, post, private_key_pem):
    """Decrypt into the folder; returns the full post dict (locked files removed)."""
    folder = Path(folder)
    fd, key_path = tempfile.mkstemp()
    try:
        os.write(fd, private_key_pem.encode())
        os.close(fd)
        password = _openssl("pkeyutl", "-decrypt", "-inkey", key_path,
                            "-pkeyopt", "rsa_padding_mode:oaep",
                            data=(folder / "key.enc").read_bytes())
    finally:
        os.unlink(key_path)
    with tempfile.NamedTemporaryFile() as pw:
        pw.write(password)
        pw.flush()
        tar_bytes = _openssl("enc", "-d", "-aes-256-cbc", "-pbkdf2", "-pass", f"file:{pw.name}",
                             data=(folder / "content.enc").read_bytes())
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        content = json.load(tar.extractfile("content.json"))
        for name in files_of(content):
            member = tar.getmember(name)
            if "/" in name or name.startswith("."):
                raise ValueError(f"bad media name {name!r}")
            (folder / name).write_bytes(tar.extractfile(member).read())
    (folder / "content.enc").unlink()
    (folder / "key.enc").unlink()
    full = {k: v for k, v in post.items() if k != "locked"}
    full.update(content)
    return full
