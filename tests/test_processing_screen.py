"""The thinking screen shows the backend's transcription, or 'Thinking...'."""

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
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
    # Something dark was drawn on the white background
    assert any(surface.get_at((x, 360))[:3] != (255, 255, 255) for x in range(0, 720, 2))


def test_recorder_without_text_does_not_crash():
    _render(ProcessingScreen(_Recorder(), None))  # used to raise AttributeError


def test_factory_passes_ai_service():
    ai = _Text("hello")
    screen = get_screen(State.PROCESSING, {}, {"audio_service": _Recorder(), "ai_service": ai})
    assert screen.text_source is ai
