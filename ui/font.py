import pygame
from pathlib import Path
from typing import Dict

# Centralized font loader and renderer. Place the TTF files under a `fonts/` directory
# in the project root: `fonts/NotoSans-Regular.ttf` and `fonts/NotoSansDevanagari-Regular.ttf`.

_FONT_CACHE: Dict[str, pygame.font.Font] = {}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Check multiple possible fonts directories (project root /fonts, project root /assets/fonts)
FONTS_DIRS = [PROJECT_ROOT / "fonts", PROJECT_ROOT / "assets" / "fonts"]

def _find_font(filename: str) -> Path:
    for d in FONTS_DIRS:
        p = d / filename
        if p.exists():
            return p
    return Path(filename)  # fallback to raw path (may not exist)

DEFAULT_LATIN = _find_font("NotoSans-Regular.ttf")
DEFAULT_DEVANAGARI = _find_font("NotoSansDevanagari-Regular.ttf")
_FONT_INFO_PRINTED = False


def _load_font(path: Path, size: int) -> pygame.font.Font:
    key = f"{path}:{size}"
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    try:
        font = pygame.font.Font(str(path), size)
    except Exception:
        # fallback to default system font
        font = pygame.font.SysFont(None, size)
    _FONT_CACHE[key] = font
    return font


def _contains_devanagari(text: str) -> bool:
    for ch in text:
        if '\u0900' <= ch <= '\u097F':
            return True
    return False


def _char_script(ch: str) -> str:
    if '\u0900' <= ch <= '\u097F':
        return 'devanagari'
    return 'latin'


def calculate_font_size(text: str, surface_width: int, surface_height: int, min_size=20, max_size=60, padding=30):
    """Calculate optimal font size for text to fit within surface dimensions.
    
    Tries progressively smaller font sizes until text fits within bounds.
    """
    if not text:
        return max_size
    
    available_width = surface_width - (padding * 2)
    available_height = surface_height - (padding * 2)
    
    # Try sizes from max to min
    for size in range(max_size, min_size - 1, -4):
        # Quick estimate: average char width ~60% of font size
        est_width = len(text) * (size * 0.6)
        
        if est_width <= available_width:
            return size
    
    return min_size


def render_text(surface: pygame.Surface, text: str, size: int, color, center=True):
    """Render `text` onto `surface` using appropriate fonts per script.

    Splits `text` into runs of Devanagari vs Latin characters and renders each
    run with the correct font, composing them horizontally. `center` may be:
      - True: center the whole composed text on `surface`
      - False: blit at (0,0)
      - (x, y): use the tuple as the center coordinates for the composed text

    Returns the composed surface and its blit rect on `surface`.
    """
    if not text:
        empty = pygame.Surface((0, 0), flags=pygame.SRCALPHA)
        rect = empty.get_rect(topleft=(0, 0))
        return empty, rect

    # Build runs by script
    runs = []
    current_script = _char_script(text[0])
    current_run = text[0]
    for ch in text[1:]:
        script = _char_script(ch)
        if script == current_script:
            current_run += ch
        else:
            runs.append((current_script, current_run))
            current_script = script
            current_run = ch
    runs.append((current_script, current_run))

    # Render each run to its surface
    run_surfs = []
    max_h = 0
    total_w = 0
    for script, run_text in runs:
        if script == 'devanagari' and DEFAULT_DEVANAGARI.exists():
            font = _load_font(DEFAULT_DEVANAGARI, size)
            global _FONT_INFO_PRINTED
            if not _FONT_INFO_PRINTED:
                try:
                    print(f"[FONT] Using Devanagari font: {DEFAULT_DEVANAGARI}", flush=True)
                except Exception:
                    pass
                _FONT_INFO_PRINTED = True
        elif DEFAULT_LATIN.exists():
            font = _load_font(DEFAULT_LATIN, size)
        else:
            font = pygame.font.SysFont(None, size)

        run_surf = font.render(run_text, True, color)
        run_surfs.append(run_surf)
        w, h = run_surf.get_size()
        total_w += w
        max_h = max(max_h, h)

    # Compose into one surface
    comp = pygame.Surface((max(1, total_w), max(1, max_h)), flags=pygame.SRCALPHA)
    comp.fill((0, 0, 0, 0))
    x = 0
    for s in run_surfs:
        y = (max_h - s.get_height()) // 2
        comp.blit(s, (x, y))
        x += s.get_width()

    # Compute placement on destination surface
    dest_rect = None
    if center is True:
        dest_rect = comp.get_rect(center=surface.get_rect().center)
    elif center is False:
        dest_rect = comp.get_rect(topleft=(0, 0))
    elif isinstance(center, tuple) and len(center) == 2:
        dest_rect = comp.get_rect(center=center)
    else:
        dest_rect = comp.get_rect(center=surface.get_rect().center)

    surface.blit(comp, dest_rect)
    return comp, dest_rect
