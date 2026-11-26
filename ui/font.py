import pygame
from pathlib import Path
from typing import Dict

# Centralized font loader and renderer. Place the TTF files under a `fonts/` directory
# in the project root: `fonts/NotoSans-Regular.ttf` and `fonts/NotoSansDevanagari-Regular.ttf`.
# assets/fonts/ holds the Hindi (Devanagari) and Kannada fonts (SIL Open Font License).

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
DEFAULT_KANNADA = _find_font("NotoSansKannada-Regular.ttf")
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


_PIL_FONTS: Dict[str, object] = {}


def _shaping_available() -> bool:
    try:
        from PIL import features
        return bool(features.check("raqm"))
    except Exception:
        return False


_SHAPING = _shaping_available()


def _render_shaped(path: Path, text: str, size: int, color) -> pygame.Surface:
    """Draw Kannada or Hindi with Pillow's text shaping (Raqm).

    pygame places letters one by one, so vowel signs overlap and joined
    letters fall apart. Raqm joins them the way the script needs.
    """
    from PIL import Image, ImageDraw, ImageFont
    key = f"{path}:{size}"
    font = _PIL_FONTS.get(key)
    if font is None:
        font = ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)
        _PIL_FONTS[key] = font
    left, top, right, bottom = font.getbbox(text)
    ascent, descent = font.getmetrics()
    dx, dy = -min(0, left), -min(0, top)
    w = max(1, right + dx)
    h = max(1, max(bottom, ascent + descent) + dy)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((dx, dy), text, font=font, fill=tuple(color[:3]) + (255,))
    return pygame.image.frombytes(img.tobytes(), img.size, "RGBA")


def _contains_devanagari(text: str) -> bool:
    for ch in text:
        if '\u0900' <= ch <= '\u097F':
            return True
    return False


def _char_script(ch: str) -> str:
    if '\u0900' <= ch <= '\u097F':
        return 'devanagari'
    if '\u0C80' <= ch <= '\u0CFF':
        return 'kannada'
    if ch.isspace() or ch in '.,!?;:\'"-()':
        return 'neutral'  # stays with the words around it
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


def ui_scale(surface: pygame.Surface) -> float:
    """Text-size multiplier for bigger screens.

    Sizes in the screens were tuned for the old 320x480 display. On a larger
    display (e.g. the 720x720 HDMI screen) text grows with the shorter side;
    it never shrinks below the original size.
    """
    w, h = surface.get_size()
    return max(1.0, min(w, h) / 480)


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

    # Build runs by script. Spaces and punctuation join the run they are in,
    # so a whole Kannada or Hindi sentence is shaped as one piece.
    runs = []
    current_script = _char_script(text[0])
    if current_script == 'neutral':
        current_script = 'latin'
    current_run = text[0]
    for ch in text[1:]:
        script = _char_script(ch)
        if script == 'neutral' or script == current_script:
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
        shaped_font = {'devanagari': DEFAULT_DEVANAGARI, 'kannada': DEFAULT_KANNADA}.get(script)
        if _SHAPING and shaped_font is not None and shaped_font.exists():
            run_surf = _render_shaped(shaped_font, run_text, size, color)
            run_surfs.append(run_surf)
            w, h = run_surf.get_size()
            total_w += w
            max_h = max(max_h, h)
            continue
        if script == 'devanagari' and DEFAULT_DEVANAGARI.exists():
            font = _load_font(DEFAULT_DEVANAGARI, size)
            global _FONT_INFO_PRINTED
            if not _FONT_INFO_PRINTED:
                try:
                    print(f"[FONT] Using Devanagari font: {DEFAULT_DEVANAGARI}", flush=True)
                except Exception:
                    pass
                _FONT_INFO_PRINTED = True
        elif script == 'kannada' and DEFAULT_KANNADA.exists():
            font = _load_font(DEFAULT_KANNADA, size)
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


_BLOCK_CACHE: Dict[tuple, tuple] = {}


def _line_surface(text: str, size: int, color):
    probe = pygame.Surface((1, 1), flags=pygame.SRCALPHA)
    return render_text(probe, text, size, color, center=False)[0]


def fit_text_block(text: str, max_width: int, max_height: int, max_size: int, min_size: int = 20,
                   color=(0, 0, 0), spacing: float = 1.12):
    """Biggest font size (stepping down from max_size) at which `text`,
    wrapped at word breaks, fits inside max_width x max_height.

    Returns (size, [line surfaces], line_step). Line heights are measured
    from the drawn lines, so tall Kannada and Hindi letters never overlap.
    Results are cached: screens can call this every frame.
    """
    key = (text, max_width, max_height, max_size, min_size, tuple(color), spacing)
    if key in _BLOCK_CACHE:
        return _BLOCK_CACHE[key]
    words = text.split()
    best = None
    for size in range(max_size, min_size - 1, -2):
        lines, current = [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or _line_surface(candidate, size, color).get_width() <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        surfs = [_line_surface(line, size, color) for line in lines]
        step = int(max([size] + [sf.get_height() for sf in surfs]) * spacing)
        widest = max([0] + [sf.get_width() for sf in surfs])
        best = (size, surfs, step)
        if step * len(surfs) <= max_height and widest <= max_width:
            break
    if len(_BLOCK_CACHE) > 64:
        _BLOCK_CACHE.clear()
    _BLOCK_CACHE[key] = best
    return best
