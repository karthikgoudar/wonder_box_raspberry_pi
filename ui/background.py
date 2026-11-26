"""The sunburst background behind the start, listening, thinking and error
screens. Sticker pictures (and story pictures) are shown without it.

SCREEN_BACKGROUND picks the image (default assets/images/background.png);
set it to "none" for plain white. The image is loaded once and scaled to
the screen size once.
"""

import os
from pathlib import Path

import pygame

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_cache = {}


def _path():
    raw = (os.getenv("SCREEN_BACKGROUND") or "").strip()
    if raw.lower() in ("none", "off", "0"):
        return None
    return Path(raw).expanduser() if raw else PROJECT_ROOT / "assets" / "images" / "background.png"


def draw_background(surface: pygame.Surface):
    """Paint the background (or white if there is none)."""
    path = _path()
    size = surface.get_size()
    key = (str(path), size)
    if key not in _cache:
        image = None
        if path is not None and path.is_file():
            try:
                image = pygame.transform.smoothscale(pygame.image.load(str(path)), size)
            except Exception as e:
                print(f"[UI] background not loaded ({path}): {e}", flush=True)
        _cache.clear()
        _cache[key] = image
    image = _cache[key]
    if image is None:
        surface.fill((255, 255, 255))
    else:
        surface.blit(image, (0, 0))
