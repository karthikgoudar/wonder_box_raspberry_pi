"""AudioService records and saves a WAV only; transcription is the backend's job."""

import sys
import time
import types
import wave

import numpy as np
import pytest

# sounddevice needs PortAudio, which CI and dev machines may lack
sys.modules.setdefault("sounddevice", types.SimpleNamespace(InputStream=None))
pytest.importorskip("scipy")

from services.audio_service import AudioService  # noqa: E402


def _wait(svc, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end and not (svc.is_done() or svc.has_failed()):
        svc.update()
        time.sleep(0.01)


def test_saves_wav_and_exposes_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    svc = AudioService()
    svc._frames = [np.zeros((4410, 1), dtype=np.int16)]
    svc._processing = True
    _wait(svc)

    assert svc.is_done() and not svc.has_failed()
    path = svc.get_wav_path()
    assert path.endswith(".wav")
    with wave.open(path) as w:
        assert w.getframerate() == 44100 and w.getnchannels() == 1


def test_no_wav_path_before_done():
    svc = AudioService()
    assert svc.get_wav_path() is None and not svc.is_done()


def test_empty_recording_fails(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    svc = AudioService()
    svc._processing = True
    _wait(svc)
    assert svc.has_failed() and "no audio" in svc.get_error()


def test_reset_clears_state(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    svc = AudioService()
    svc._frames = [np.zeros((100, 1), dtype=np.int16)]
    svc._processing = True
    _wait(svc)
    svc.reset()
    assert not svc.is_done() and svc.get_wav_path() is None
