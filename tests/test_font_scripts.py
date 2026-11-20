"""Kannada and Hindi words are drawn with their own fonts, not empty boxes."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from ui import font as F

KANNADA = "ಕೋತಿ ಮರಿ ಜೋರಾಗಿ ಹಾಡು ಹೇಳ್ತಾ ಇದೆ."
HINDI = "हाथी स्काई में उड़ रहा है"


@pytest.fixture(autouse=True)
def _pygame():
    pygame.init()
    yield


def test_fonts_are_bundled():
    assert F.DEFAULT_KANNADA.exists() and F.DEFAULT_DEVANAGARI.exists()


def test_script_of_each_letter():
    assert F._char_script("ಕ") == "kannada"
    assert F._char_script("ह") == "devanagari"
    assert F._char_script("a") == "latin"
    assert F._char_script(" ") == "neutral" and F._char_script(".") == "neutral"


def _boxes(text):
    """Draw text with the fallback font; missing letters all look the same."""
    f = pygame.font.Font(None, 40)
    return [pygame.image.tobytes(f.render(ch, True, (0, 0, 0)), "RGBA") for ch in text]


@pytest.mark.parametrize("text,font_name", [
    (KANNADA, "NotoSansKannada-Regular.ttf"),
    (HINDI, "NotoSansDevanagari-Regular.ttf"),
])
def test_sentence_is_one_shaped_run_in_its_own_font(text, font_name, monkeypatch):
    assert F._SHAPING, "Pillow without Raqm: Kannada would be drawn unjoined"
    used = []
    real = F._render_shaped
    monkeypatch.setattr(F, "_render_shaped",
                        lambda path, t, size, color: used.append((path.name, t)) or real(path, t, size, color))
    F.render_text(pygame.Surface((720, 720)), text, 40, (0, 0, 0))
    assert used == [(font_name, text)]  # spaces did not split the sentence


def test_shaping_joins_kannada_letters():
    from PIL import ImageFont
    basic = ImageFont.truetype(str(F.DEFAULT_KANNADA), 40, layout_engine=ImageFont.Layout.BASIC)
    joined = F._render_shaped(F.DEFAULT_KANNADA, "ಕ್ಕ", 40, (0, 0, 0))
    assert joined.get_width() < basic.getlength("ಕ್ಕ")  # ಕ + ್ + ಕ became one joined shape
    spaced = F._render_shaped(F.DEFAULT_KANNADA, "ಕ ಕ", 40, (0, 0, 0))
    tight = F._render_shaped(F.DEFAULT_KANNADA, "ಕಕ", 40, (0, 0, 0))
    assert spaced.get_width() > tight.get_width()  # the space is kept


def test_kannada_letters_are_real_shapes():
    f = pygame.font.Font(str(F.DEFAULT_KANNADA), 40)
    shapes = {pygame.image.tobytes(f.render(ch, True, (0, 0, 0)), "RGBA") for ch in "ಕಮರಹ"}
    assert len(shapes) == 4  # four different letters, not four identical boxes
