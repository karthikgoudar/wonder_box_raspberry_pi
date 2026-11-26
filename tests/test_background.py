"""The sunburst background is behind the text screens, not the pictures."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from ui import background


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    pygame.init()
    background._cache.clear()
    yield
    background._cache.clear()


def _render(screen, size=(720, 720)):
    surface = pygame.Surface(size)
    screen.render(surface)
    return surface


def test_image_is_in_the_app():
    assert (background.PROJECT_ROOT / "assets" / "images" / "background.png").is_file()


@pytest.mark.parametrize("make", [
    lambda: __import__("ui.idle_screen", fromlist=["x"]).IdleScreen(lambda: None),
    lambda: __import__("ui.listening_screen", fromlist=["x"]).ListeningScreen(),
    lambda: __import__("ui.processing_screen", fromlist=["x"]).ProcessingScreen(None, None),
    lambda: __import__("ui.error_screen", fromlist=["x"]).ErrorScreen({}),
])
def test_text_screens_have_the_background(make, monkeypatch):
    monkeypatch.delenv("SCREEN_BACKGROUND", raising=False)
    surface = _render(make())
    corner = surface.get_at((5, 5))[:3]
    assert corner != (255, 255, 255)                 # not plain white
    assert surface.get_size() == (720, 720)


def test_background_scales_to_other_screen_sizes(monkeypatch):
    monkeypatch.delenv("SCREEN_BACKGROUND", raising=False)
    s = pygame.Surface((480, 320))
    background.draw_background(s)
    assert s.get_at((5, 5))[:3] != (255, 255, 255)


def test_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("SCREEN_BACKGROUND", "none")
    s = pygame.Surface((100, 100))
    background.draw_background(s)
    assert s.get_at((5, 5))[:3] == (255, 255, 255)


def test_missing_file_falls_back_to_white(monkeypatch, tmp_path):
    monkeypatch.setenv("SCREEN_BACKGROUND", str(tmp_path / "nope.png"))
    s = pygame.Surface((100, 100))
    background.draw_background(s)
    assert s.get_at((5, 5))[:3] == (255, 255, 255)


def test_sticker_picture_fills_the_screen_without_background(monkeypatch):
    monkeypatch.delenv("SCREEN_BACKGROUND", raising=False)
    from ui import current_image
    from ui.displaying_screen import DisplayingScreen
    picture = pygame.Surface((720, 720)); picture.fill((10, 200, 30))
    current_image.set_image(picture)
    try:
        surface = _render(DisplayingScreen())
        assert surface.get_at((5, 5))[:3] == (10, 200, 30) and surface.get_at((715, 715))[:3] == (10, 200, 30)
    finally:
        current_image.set_image(None)
