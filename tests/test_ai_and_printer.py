"""ai_service (backend-driven) and printer_service strip streaming."""

import io
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from services import printer_service as ps
from services.ai_service import AIService
from services.backend_client import STRIP_BYTES, BackendError, StickerResult

STRIP = b"\x1d\x76\x30\x00\x30\x00\x18\x00" + b"\x00" * (STRIP_BYTES - 8)


def _png():
    pygame.init()
    pygame.display.set_mode((1, 1))
    surf = pygame.Surface((8, 8))
    buf = io.BytesIO()
    pygame.image.save(surf, buf, "x.png")
    return buf.getvalue()


class FakeClient:
    def __init__(self, fail=None, strips_fail=False, delay=0):
        self.fail, self.strips_fail, self.delay = fail, strips_fail, delay
        self.submitted = []

    def submit_sticker(self, wav):
        self.submitted.append(wav)
        time.sleep(self.delay)
        if self.fail:
            raise self.fail
        return StickerResult("j1", "s1", "a penguin", "en", "/i.png", "/p.bin", None)

    def download(self, url):
        return _png()

    def download_print_strips(self, url):
        if self.strips_fail:
            raise BackendError("bad payload")
        return [STRIP] * 16


def _wait(ai, t=3):
    end = time.time() + t
    while time.time() < end and not (ai.is_done() or ai.has_failed()):
        time.sleep(0.01)


def test_success_exposes_image_strips_text():
    c = FakeClient()
    ai = AIService(client=c)
    ai.start_generation("rec.wav")
    _wait(ai)
    assert ai.is_done() and not ai.has_failed()
    assert c.submitted == ["rec.wav"]
    assert ai.get_image() is not None
    assert len(ai.get_print_strips()) == 16
    assert ai.get_text() == "a penguin"


def test_backend_error_sets_failed():
    ai = AIService(client=FakeClient(fail=BackendError("HTTP 500: boom", 500)))
    ai.start_generation("rec.wav")
    _wait(ai)
    assert ai.has_failed() and "boom" in ai.get_error()


def test_bad_print_payload_still_shows_image():
    ai = AIService(client=FakeClient(strips_fail=True))
    ai.start_generation("rec.wav")
    _wait(ai)
    assert ai.is_done() and ai.get_image() is not None
    assert ai.get_print_strips() is None


def test_reset_drops_in_flight_result():
    ai = AIService(client=FakeClient(delay=0.2))
    ai.start_generation("rec.wav")
    ai.reset()
    time.sleep(0.5)
    assert not ai.is_done() and ai.get_image() is None


def test_missing_config_disables_without_crashing(monkeypatch):
    monkeypatch.delenv("BACKEND_URL", raising=False)
    monkeypatch.delenv("DEVICE_TOKEN", raising=False)
    ai = AIService()
    assert ai.has_failed() and "BACKEND_URL" in ai.get_error()
    ai.start_generation("rec.wav")  # must not raise
    assert ai.has_failed()


class FakeSerial:
    is_open = True

    def __init__(self):
        self.writes = []

    def write(self, b):
        self.writes.append((time.time(), bytes(b)))

    def flush(self):
        pass


def test_strips_written_whole_with_pacing(monkeypatch):
    monkeypatch.setattr(ps, "PRINTER_SIMULATE", False)
    monkeypatch.setattr(ps, "_HAS_SERIAL", True)
    monkeypatch.setattr(ps, "PRINTER_STRIP_DELAY", 0.02)
    p = ps.PrinterService(port="fake")
    p._serial = FakeSerial()
    p.start_print_strips([STRIP] * 4, feed=0)
    p._thread.join(3)
    assert p.is_done() and not p.has_failed()
    strip_writes = [(t, b) for t, b in p._serial.writes if len(b) == STRIP_BYTES]
    assert len(strip_writes) == 4 and all(b == STRIP for _, b in strip_writes)
    gaps = [b[0] - a[0] for a, b in zip(strip_writes, strip_writes[1:])]
    assert all(g >= 0.018 for g in gaps)


def test_strip_print_simulated(monkeypatch):
    monkeypatch.setattr(ps, "PRINTER_SIMULATE", True)
    p = ps.PrinterService(port="fake", simulate_duration=0.01)
    p.start_print_strips([STRIP])
    p._thread.join(2)
    assert p.is_done()
