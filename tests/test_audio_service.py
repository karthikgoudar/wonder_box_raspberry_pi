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
        assert w.getframerate() == 16000 and w.getnchannels() == 1
        assert w.getnframes() == 4410 // 3  # 48 kHz recording shrunk 3x


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


def test_test_wav_replaces_microphone(monkeypatch, tmp_path):
    src = tmp_path / "in.wav"
    src.write_bytes(b"RIFFfake")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUDIO_TEST_WAV", str(src))
    svc = AudioService()
    svc.start_recording()  # must not open a microphone
    assert svc._stream is None and svc._recording
    svc.stop_recording()
    _wait(svc)
    assert svc.is_done() and open(svc.get_wav_path(), "rb").read() == b"RIFFfake"


def test_audio_device_from_env(monkeypatch):
    monkeypatch.setenv("AUDIO_DEVICE", "0")
    assert AudioService().device == 0


def test_audio_device_by_name(monkeypatch):
    monkeypatch.setenv("AUDIO_DEVICE", "voicehat")
    assert AudioService().device == "voicehat"


def test_audio_device_unset_uses_default(monkeypatch):
    monkeypatch.delenv("AUDIO_DEVICE", raising=False)
    assert AudioService().device is None


def _save(svc, frames):
    svc._frames = [frames]
    svc._processing = True
    _wait(svc)
    assert svc.is_done(), svc.get_error()
    with wave.open(svc.get_wav_path()) as w:
        assert w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def test_keeps_mic_channel_from_stereo(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUDIO_MIC_CHANNEL", "0")
    t = np.linspace(0, 1, 4800, dtype=np.float32)
    left = 0.5 * np.sin(2 * np.pi * 440 * t)
    stereo = np.stack([left, np.zeros_like(left)], axis=1)
    out = _save(AudioService(), stereo)
    assert np.abs(out).max() > 20000  # left channel kept, not the silent right


def test_quiet_mic_is_boosted_but_capped(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUDIO_MAX_GAIN", "40")
    t = np.linspace(0, 1, 4800, dtype=np.float32)
    quiet = (0.02 * np.sin(2 * np.pi * 440 * t)).reshape(-1, 1)  # about -34 dBFS
    out = _save(AudioService(), quiet)
    assert 0.75 * 32767 < np.abs(out).max() <= 32767  # 0.02 x 40 = about 80%
    tiny = (0.0001 * np.sin(2 * np.pi * 440 * t)).reshape(-1, 1)
    out = _save(AudioService(), tiny)
    assert np.abs(out).max() < 0.01 * 32767  # near-silence capped at 40x


def test_save_rate_zero_keeps_recording_rate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUDIO_SAVE_RATE", "0")
    svc = AudioService()
    _save(svc, np.zeros((4800, 1), dtype=np.float32))
    with wave.open(svc.get_wav_path()) as w:
        assert w.getframerate() == 48000 and w.getnframes() == 4800


def test_downsampled_speech_keeps_its_loudness(monkeypatch, tmp_path):
    """A 440 Hz tone survives the 48 to 16 kHz step (filtering keeps speech)."""
    monkeypatch.chdir(tmp_path)
    t = np.arange(48000, dtype=np.float32) / 48000
    tone = (0.5 * np.sin(2 * np.pi * 440 * t)).reshape(-1, 1)
    out = _save(AudioService(), tone)
    assert len(out) == 16000
    assert np.abs(out[1000:-1000]).max() > 0.8 * 32767  # boosted to about 90%
