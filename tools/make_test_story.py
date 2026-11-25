"""Make a small English test story in the story folder layout.

Runs on a Mac (uses the built-in `say` voice and ffmpeg). The pictures are
simple black line drawings, like the real scene pictures should be.

    venv/bin/python tools/make_test_story.py [stories_dir]

Then copy stories/en/00_test_story to the Pi's stories folder.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

SCENES = [
    ("A little star woke up in the night sky. She yawned and stretched her five shiny points.",
     "star"),
    ("Down below, she saw a tiny house with a warm yellow window. A girl was looking up at her.",
     "house"),
    ("The star twinkled her brightest twinkle. The girl smiled and waved goodnight. The end.",
     "moon"),
]
TITLE = "The Little Star\nThe Little Star\n"


def draw(kind: str, path: Path, size=768, width=14):
    img = Image.new("L", (size, size), 255)
    d = ImageDraw.Draw(img)
    c, r = size // 2, size // 3
    if kind == "star":
        import math
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.45
            pts.append((c + rr * math.cos(a), c + rr * math.sin(a)))
        d.line(pts + [pts[0]], fill=0, width=width, joint="curve")
        d.ellipse((c - 60, c - 30, c - 30, c), outline=0, width=width // 2)
        d.ellipse((c + 30, c - 30, c + 60, c), outline=0, width=width // 2)
        d.arc((c - 50, c, c + 50, c + 60), 20, 160, fill=0, width=width // 2)
    elif kind == "house":
        d.rectangle((c - r, c - 20, c + r, c + r), outline=0, width=width)
        d.line([(c - r - 30, c - 10), (c, c - r), (c + r + 30, c - 10)], fill=0, width=width, joint="curve")
        d.rectangle((c - 40, c + r - 140, c + 40, c + r), outline=0, width=width)
        d.rectangle((c + 80, c + 30, c + 180, c + 120), outline=0, width=width)
    else:
        d.ellipse((c - r, c - r, c + r, c + r), outline=0, width=width)
        d.ellipse((c - r + 120, c - r - 40, c + r + 120, c + r - 40), fill=255)
        d.arc((c - r, c - r, c + r, c + r), 90, 270, fill=0, width=width)
    img.save(path)


def main(root: Path):
    for tool in ("say", "ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} is needed (Mac with ffmpeg installed)")
    folder = root / "en" / "00_test_story"
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "images").mkdir(parents=True)
    (folder / "text").mkdir()
    (folder / "title.txt").write_text(TITLE, encoding="utf-8")

    starts, t = [], 0.0
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, (words, kind) in enumerate(SCENES, 1):
            stem = f"scene_{i:02d}"
            draw(kind, folder / "images" / f"{stem}.png")
            (folder / "text" / f"{stem}.txt").write_text(words + "\n", encoding="utf-8")
            aiff = Path(tmp) / f"{stem}.aiff"
            subprocess.run(["say", "-o", str(aiff), words], check=True)
            wav = Path(tmp) / f"{stem}.wav"  # same format for every part, 0.8 s pause after
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(aiff), "-af", "apad=pad_dur=0.8",
                            "-ar", "44100", "-ac", "1", str(wav)], check=True)
            length = float(subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)],
                check=True, capture_output=True, text=True).stdout)
            starts.append((stem, t))
            t += length
            parts.append(wav)
        listing = Path(tmp) / "parts.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                        "-codec:a", "libmp3lame", "-q:a", "4", str(folder / "story.mp3")], check=True)
    (folder / "timings.txt").write_text(
        "".join(f"{stem} {int(s // 60)}:{s % 60:04.1f}\n" for stem, s in starts), encoding="utf-8")
    print(f"made {folder} ({t:.1f} s)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "stories")
