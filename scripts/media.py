"""Video helpers for new_post.py (ffmpeg).

Instagram's API can't attach songs from Instagram's music library, so "music" here means
baking your own audio file into the video before it's scheduled. Only use audio you have
the rights to - Instagram may mute or block posts with copyrighted songs.
"""
import json
import shutil
import subprocess
import sys

REEL_W, REEL_H = 1080, 1920


def ffmpeg_bin(name="ffmpeg"):
    path = shutil.which(name)
    if path:
        return path
    try:  # pip install imageio-ffmpeg ships a static ffmpeg (no ffprobe)
        import imageio_ffmpeg
        if name == "ffmpeg":
            return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    sys.exit(f"{name} not found - install ffmpeg (or: pip install imageio-ffmpeg)")


def run(args):
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", *args], check=True)


def has_audio(video):
    if not shutil.which("ffprobe"):
        return True  # assume yes; amix fails loudly if not
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=index", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True).stdout
    return bool(json.loads(out).get("streams"))


AUDIO_OUT = ["-c:a", "aac", "-b:a", "192k", "-ar", "44100"]


def add_music(video, music, dest, volume=1.0, keep_original=False):
    """Put `music` under `video` (looped/trimmed to the video's length), fading out at the end."""
    if keep_original and has_audio(video):
        audio = (f"[0:a]volume=1[a0];[1:a]volume={volume}[a1];"
                 f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[a]")
    else:
        audio = f"[1:a]volume={volume}[a]"
    run(["-i", str(video), "-stream_loop", "-1", "-i", str(music),
         "-filter_complex", audio, "-map", "0:v", "-map", "[a]",
         "-c:v", "copy", *AUDIO_OUT, "-shortest", "-movflags", "+faststart", str(dest)])


def slideshow(images, dest, seconds=3.0, music=None, volume=1.0, pad_color="black"):
    """Turn images into a 9:16 Reel, each slide `seconds` long, optionally with music."""
    args = []
    for img in images:
        args += ["-loop", "1", "-t", str(seconds), "-i", str(img)]
    if music:
        args += ["-stream_loop", "-1", "-i", str(music)]
    n = len(images)
    chains = "".join(
        f"[{i}:v]scale={REEL_W}:{REEL_H}:force_original_aspect_ratio=decrease,"
        f"pad={REEL_W}:{REEL_H}:(ow-iw)/2:(oh-ih)/2:color={pad_color},setsar=1,fps=30[v{i}];"
        for i in range(n))
    graph = chains + "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,format=yuv420p[v]"
    total = seconds * n
    maps = ["-map", "[v]"]
    if music:
        graph += f";[{n}:a]volume={volume},afade=t=out:st={max(total - 1.5, 0)}:d=1.5[a]"
        maps += ["-map", "[a]", *AUDIO_OUT]
    run([*args, "-filter_complex", graph, *maps, "-t", str(total),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
         "-movflags", "+faststart", str(dest)])
