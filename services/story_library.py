"""Pre-recorded stories kept on the Pi.

Folder layout (the same in Google Drive and on the Pi):

    stories/
      en/  kn/  hi/                    one folder per language
        01_ane_mattu_ili/              number + short name
          title.txt                    line 1: title; line 2: English title
          story.mp3                    the whole story, one recording
          timings.txt                  "scene_01 0:00" - when each scene starts
          images/scene_01.png          shown and printed when scene 1 starts
          images/sticker.png           optional, printed after the last scene
          text/scene_01.txt            words narrated in scene 1, shown on screen

The app works everything out from the file names. Check a folder with:

    python -m services.story_library            # checks STORIES_DIR
    python -m services.story_library some/dir   # checks another folder
"""

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("en", "kn", "hi")
AUDIO_NAMES = ("story.mp3", "story.ogg", "story.wav")
IMAGE_EXTS = (".png", ".jpg", ".jpeg")

_SCENE_RE = re.compile(r"^scene_(\d+)$")
_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+|\n+")


class StoryError(ValueError):
    """A story folder that does not follow the layout."""


def stories_dir() -> Path:
    raw = os.getenv("STORIES_DIR")
    return Path(raw).expanduser() if raw else PROJECT_ROOT / "stories"


def parse_time(value: str) -> float:
    """'0:18.5' -> 18.5, '1:02' -> 62.0, '41' -> 41.0."""
    value = value.strip()
    parts = value.split(":")
    if len(parts) > 3 or not all(p.strip() for p in parts):
        raise ValueError(value)
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + float(p)
    if seconds < 0:
        raise ValueError(value)
    return seconds


def split_sentences(text: str) -> list[str]:
    """Split a scene's words into sentences for the screen."""
    return [s.strip() for s in _SENTENCE_END.split(text or "") if s and s.strip()]


@dataclass
class Scene:
    number: int
    start: float              # seconds from the start of story audio
    image: Path
    text: str = ""
    sentences: list[str] = field(default_factory=list)


@dataclass
class Story:
    folder: Path
    language: str
    title: str
    title_en: str
    audio: Path
    scenes: list[Scene]
    sticker: Optional[Path] = None

    @property
    def name(self) -> str:
        return f"{self.language}/{self.folder.name}"


def _find_image(images: Path, stem: str) -> Optional[Path]:
    for ext in IMAGE_EXTS:
        p = images / f"{stem}{ext}"
        if p.is_file():
            return p
    return None


def load_story(folder: Path, language: Optional[str] = None) -> Story:
    """Read one story folder. Raises StoryError saying what is wrong."""
    folder = Path(folder)
    language = language or folder.parent.name
    problems = []

    title_file = folder / "title.txt"
    lines = []
    if title_file.is_file():
        lines = [l.strip() for l in title_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        problems.append("title.txt is missing")
    title = lines[0] if lines else folder.name
    title_en = lines[1] if len(lines) > 1 else title

    audio = next((folder / n for n in AUDIO_NAMES if (folder / n).is_file()), None)
    if audio is None:
        problems.append("story.mp3 is missing")

    timings_file = folder / "timings.txt"
    timings = []
    if not timings_file.is_file():
        problems.append("timings.txt is missing")
    else:
        for n, raw in enumerate(timings_file.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            bits = line.split()
            m = _SCENE_RE.match(bits[0]) if len(bits) == 2 else None
            if not m:
                problems.append(f"timings.txt line {n}: expected 'scene_01 0:00', got '{line}'")
                continue
            try:
                timings.append((int(m.group(1)), bits[0], parse_time(bits[1])))
            except ValueError:
                problems.append(f"timings.txt line {n}: '{bits[1]}' is not a time like 0:18.5")
        if not timings and not problems:
            problems.append("timings.txt has no scenes")
        starts = [t for _, _, t in timings]
        if starts != sorted(starts):
            problems.append("timings.txt: scene times must go up")
        if timings and starts[0] > 0.5:
            problems.append("timings.txt: the first scene should start at 0:00")

    images, texts = folder / "images", folder / "text"
    scenes = []
    for number, stem, start in timings:
        image = _find_image(images, stem)
        if image is None:
            problems.append(f"images/{stem}.png is missing")
        text_file = texts / f"{stem}.txt"
        text = text_file.read_text(encoding="utf-8").strip() if text_file.is_file() else ""
        if not text:
            problems.append(f"text/{stem}.txt is missing or empty")
        scenes.append(Scene(number, start, image, text, split_sentences(text)))

    if problems:
        raise StoryError(f"{language}/{folder.name}: " + "; ".join(problems))
    return Story(folder, language, title, title_en, audio, scenes, _find_image(images, "sticker"))


def list_stories(root: Optional[Path] = None, language: Optional[str] = None, report=None) -> list[Story]:
    """Every valid story, sorted by language then folder name.

    Broken folders are skipped; `report(message)` hears why.
    """
    root = Path(root) if root else stories_dir()
    found = []
    for lang in LANGUAGES:
        if language and lang != language:
            continue
        lang_dir = root / lang
        if not lang_dir.is_dir():
            continue
        for folder in sorted(p for p in lang_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            try:
                found.append(load_story(folder, lang))
            except StoryError as e:
                if report:
                    report(str(e))
    return found


class StoryPicker:
    """Takes turns through the stories of a language so a demo shows each one."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root
        self._next = {}

    def pick(self, language: Optional[str]) -> Optional[Story]:
        report = lambda msg: print(f"[STORY] skipped: {msg}", flush=True)
        for lang in [language, "en", None]:
            if lang is not None and lang not in LANGUAGES:
                continue
            stories = list_stories(self.root, lang, report=report)
            if stories:
                key = lang or "*"
                i = self._next.get(key, 0) % len(stories)
                self._next[key] = i + 1
                if lang != language:
                    print(f"[STORY] no {language} story; playing {stories[i].name}", flush=True)
                return stories[i]
        return None


def _check(root: Path) -> int:
    print(f"Checking stories in {root}")
    problems = []
    stories = list_stories(root, report=problems.append)
    for s in stories:
        extra = " + end sticker" if s.sticker else ""
        print(f"  OK   {s.name}: '{s.title_en}', {len(s.scenes)} scenes{extra}")
    for p in problems:
        print(f"  FIX  {p}")
    if not stories and not problems:
        print("  No stories found (expected folders like en/01_name/)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(_check(Path(sys.argv[1]) if len(sys.argv) > 1 else stories_dir()))
