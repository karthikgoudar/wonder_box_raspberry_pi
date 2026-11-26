"""The thinking screen shows the backend's transcription, or 'Thinking...'."""

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ["SCREEN_BACKGROUND"] = "none"   # layout checks look for ink on plain white
pygame = pytest.importorskip("pygame")

from ui.processing_screen import ProcessingScreen  # noqa: E402
from ui.screen_factory import get_screen  # noqa: E402
from core.states import State  # noqa: E402


class _Text:
    def __init__(self, text):
        self.text = text

    def get_text(self):
        return self.text


class _Recorder:
    """Like AudioService: finished recording, but has no get_text()."""

    def is_done(self):
        return True


def _render(screen):
    pygame.init()
    surface = pygame.Surface((720, 720))
    screen.render(surface)
    return surface


def test_shows_text_from_ai_service():
    surface = _render(ProcessingScreen(_Recorder(), _Text("A happy cat on a rocket")))
    # Something dark was drawn on the white background (text starts top left)
    assert any(surface.get_at((x, y))[:3] != (255, 255, 255) for x in range(0, 720, 4) for y in range(0, 360, 4))


def test_recorder_without_text_does_not_crash():
    _render(ProcessingScreen(_Recorder(), None))  # used to raise AttributeError


def test_factory_passes_ai_service():
    ai = _Text("hello")
    screen = get_screen(State.PROCESSING, {}, {"audio_service": _Recorder(), "ai_service": ai})
    assert screen.text_source is ai


LONG = ("A big friendly dragon with purple wings flying over a busy city full of tall buildings while "
        "children wave from the windows and a little dog chases a red balloon down the street on a sunny afternoon")


def _ink_box(surface):
    """Bounding box of everything that is not white."""
    w, h = surface.get_size()
    xs, ys = [], []
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            if surface.get_at((x, y))[:3] != (255, 255, 255):
                xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def test_words_start_top_left():
    left, top, right, bottom = _ink_box(_render(ProcessingScreen(None, _Text("A lion"))))
    assert left < 60 and top < 80             # starts at the top left, not centred
    assert bottom < 300                       # short text stays at the top


def test_short_words_are_big_and_long_ones_shrink_to_fit():
    from ui.font import fit_text_block
    short, _, _ = fit_text_block("A lion", 660, 660, int(720 * 0.30), 20)    # very short: bigger limit
    long_size, lines, step = fit_text_block(LONG, 660, 660, int(720 * 0.18), 20)
    assert short >= 200 and long_size < short
    assert step * len(lines) <= 660 and all(l.get_width() <= 660 for l in lines)
    assert " ".join(LONG.split()) and len(lines) > 3     # wrapped, nothing dropped
    left, top, right, bottom = _ink_box(_render(ProcessingScreen(None, _Text(LONG))))
    assert right < 720 - 20 and bottom < 720 - 20        # stays inside the screen


def test_start_screen_says_press_to_start_centred_on_one_line():
    from ui import idle_screen
    assert idle_screen.START_TEXT == "Press to Start"
    left, top, right, bottom = _ink_box(_render(idle_screen.IdleScreen(lambda: None)))
    assert 0.55 * 720 <= right - left <= 0.8 * 720      # about 70% of the width
    assert bottom - top < 120                          # one line
    assert abs((left + right) / 2 - 360) < 15 and abs((top + bottom) / 2 - 360) < 15   # centred both ways


def test_max_lines_keeps_text_on_one_line():
    from ui.font import fit_text_block
    _, two, _ = fit_text_block("Press to Start", 400, 400, 120, 10)
    _, one, _ = fit_text_block("Press to Start", 400, 400, 120, 10, max_lines=1)
    assert len(two) == 2 and len(one) == 1 and one[0].get_width() <= 400
