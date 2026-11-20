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


class FakeStreamClient(FakeClient):
    """Backend in stream mode: the words arrive before the picture."""

    def __init__(self, gate=None, **kw):
        super().__init__(**kw)
        self.gate = gate  # threading.Event; picture waits until it is set

    def submit_sticker(self, wav):
        raise AssertionError("stream mode should not use direct submit")

    def submit_sticker_stream(self, wav):
        self.submitted.append(wav)
        yield "job", {"job_id": "j2"}
        yield "status", {"state": "processing"}
        yield "text", {"text": "a lion playing football", "language": "en"}
        if self.gate:
            self.gate.wait(3)
        if self.fail:
            raise self.fail
        yield "image_ready", {"image_url": "/i.png", "print_url": "/p.bin"}
        yield "done", {"sticker_id": "s2", "image_url": "/i.png", "print_url": "/p.bin"}


def test_stream_shows_words_before_picture(monkeypatch):
    import threading
    monkeypatch.delenv("AI_BACKEND_MODE", raising=False)
    gate = threading.Event()
    ai = AIService(client=FakeStreamClient(gate=gate))
    ai.start_generation("rec.wav")
    end = time.time() + 3
    while time.time() < end and ai.get_text() is None:
        time.sleep(0.01)
    assert ai.get_text() == "a lion playing football"
    assert not ai.is_done() and ai.get_image() is None  # picture still coming
    gate.set()
    _wait(ai)
    assert ai.is_done() and ai.get_image() is not None
    assert len(ai.get_print_strips()) == 16


def test_stream_error_after_words_sets_failed(monkeypatch):
    monkeypatch.delenv("AI_BACKEND_MODE", raising=False)
    ai = AIService(client=FakeStreamClient(fail=BackendError("Image generation failed")))
    ai.start_generation("rec.wav")
    _wait(ai)
    assert ai.has_failed() and "Image generation failed" in ai.get_error()


def test_direct_mode_setting_skips_stream(monkeypatch):
    monkeypatch.setenv("AI_BACKEND_MODE", "direct")

    class Both(FakeClient):
        def submit_sticker_stream(self, wav):
            raise AssertionError("direct mode should not stream")

    ai = AIService(client=Both())
    ai.start_generation("rec.wav")
    _wait(ai)
    assert ai.is_done() and ai.get_text() == "a penguin"


class FakeSerial:
    is_open = True

    def __init__(self):
        self.writes = []

    def write(self, b):
        self.writes.append((time.time(), bytes(b)))

    def flush(self):
        pass


def test_strips_written_whole_with_pacing(monkeypatch):
    monkeypatch.setattr(ps, "PRINTER_IMAGE_MODE", "raster")
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


def _raster(width_bytes, height, black):
    """1-bit rows with the given (x, y) dots black."""
    rows = bytearray(width_bytes * height)
    for x, y in black:
        rows[y * width_bytes + x // 8] |= 0x80 >> (x % 8)
    return bytes(rows)


def test_band_puts_top_left_and_bottom_right_dots_in_place():
    data = _raster(48, 24, [(0, 0), (383, 23), (5, 9)])
    out = ps.raster_to_bands(data, 48, 24)
    assert out[:5] == b"\x1b\x2a\x21\x80\x01"  # ESC * 33, 384 columns
    cols = out[5:-1]
    assert len(cols) == 384 * 3 and out[-1:] == b"\n"
    assert cols[0:3] == b"\x80\x00\x00"        # x=0, y=0: top bit
    assert cols[5 * 3 + 1] == 0x40              # x=5, y=9: second byte, bit 1
    assert cols[383 * 3:] == b"\x00\x00\x01"    # x=383, y=23: last bit


def test_short_last_band_is_padded_with_white():
    out = ps.raster_to_bands(_raster(48, 30, [(0, 29)]), 48, 30)
    bands = out.split(b"\x1b\x2a\x21\x80\x01")[1:]
    assert len(bands) == 2 and all(len(b) == 384 * 3 + 1 for b in bands)
    assert bands[1][0:3] == b"\x04\x00\x00"     # row 29 = 6th row of band 2


def test_strip_to_bands_reads_backend_header():
    strip = b"\x1d\x76\x30\x00" + bytes([48, 0, 24, 0]) + _raster(48, 24, [(0, 0)])
    assert ps.strip_to_bands(strip) == ps.raster_to_bands(strip[8:], 48, 24)
    with pytest.raises(ValueError):
        ps.strip_to_bands(b"junk")


def test_band_mode_is_the_default_for_strips(monkeypatch):
    monkeypatch.setattr(ps, "PRINTER_IMAGE_MODE", "band")
    monkeypatch.setattr(ps, "PRINTER_SIMULATE", False)
    monkeypatch.setattr(ps, "_HAS_SERIAL", True)
    monkeypatch.setattr(ps, "PRINTER_STRIP_DELAY", 0)
    strip = b"\x1d\x76\x30\x00" + bytes([48, 0, 24, 0]) + b"\xff" * (48 * 24)
    p = ps.PrinterService(port="fake")
    p._serial = FakeSerial()
    p.start_print_strips([strip] * 2, feed=0)
    p._thread.join(3)
    assert p.is_done() and not p.has_failed()
    sent = b"".join(b for _, b in p._serial.writes)
    assert b"\x1d\x76\x30" not in sent                  # no raster rows
    assert sent.count(b"\x1b\x2a\x21") == 2             # one band per strip
    assert b"\x1b\x33\x18" in sent and sent.rstrip(b"\n").endswith(b"\x1b\x32")


def test_language_refusal_keeps_backend_code_and_shows_friendly_screen(monkeypatch):
    monkeypatch.delenv("AI_BACKEND_MODE", raising=False)
    err = BackendError("Please speak in English, Kannada or Hindi", code="LANGUAGE_NOT_SUPPORTED")
    ai = AIService(client=FakeStreamClient(fail=err))
    ai.start_generation("rec.wav")
    _wait(ai)
    assert ai.has_failed() and ai.get_error_code() == "LANGUAGE_NOT_SUPPORTED"

    from ui.error_screen import ErrorScreen
    from ui.screen_factory import get_screen
    from core.states import State
    screen = get_screen(State.ERROR, {"reset": lambda: None}, {"ai_service": ai})
    assert screen.lines == ("Please speak in English,", "Kannada or Hindi")
    screen.render(pygame.Surface((720, 720)))  # draws without error

    ai.reset()
    assert ai.get_error_code() is None
    assert ErrorScreen({}, ai).lines is None  # other failures keep the usual message
    assert ErrorScreen({}).lines is None
