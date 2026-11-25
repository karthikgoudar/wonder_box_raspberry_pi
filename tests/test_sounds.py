"""App sounds and the tool that makes them from Gemini tracks."""

import sys
from pathlib import Path

import numpy as np
import pytest

from services.sound_service import SoundService

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import prepare_sounds as ps  # noqa: E402

RATE = ps.RATE


# ── Sound service (fake mixer) ───────────────────────────────────────────────

class FakeSound:
    def __init__(self, path=None, buffer=None):
        self.path, self.volume = (Path(path).name if path else "silence"), None

    def set_volume(self, v):
        self.volume = v


class FakeChannel:
    def __init__(self):
        self.log = []
        self.queued = None

    def play(self, sound, loops=0, fade_ms=0):
        self.queued = None                      # like pygame: play() clears the queue
        self.log.append(("play", sound.path, loops))

    def queue(self, sound):
        self.queued = sound
        self.log.append(("queue", sound.path))

    def get_queue(self):
        return self.queued

    def fadeout(self, ms):
        self.log.append(("fadeout",))

    def stop(self):
        self.log.append(("stop",))


class FakeMixer:
    def __init__(self):
        self.channel = FakeChannel()
        self.Sound = FakeSound

    def get_init(self):
        return True

    def init(self):
        pass

    def Channel(self, n):
        return self.channel

    def set_reserved(self, n):
        pass


def _service(tmp_path, names=("boot.wav", "waiting_loop.wav", "ready.wav")):
    for n in names:
        (tmp_path / n).write_bytes(b"RIFF")
    mixer = FakeMixer()
    return SoundService(tmp_path, mixer), mixer.channel.log


def test_boot_wait_and_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("SOUND_VOLUME", "0.5")
    s, log = _service(tmp_path)
    assert all(snd.volume == 0.5 for snd in s._sounds.values())
    s.play_boot()
    s.start_waiting()
    s.start_waiting()                       # already looping: not restarted
    s.play_ready()
    assert log == [("play", "boot.wav", 0), ("play", "waiting_loop.wav", -1), ("play", "ready.wav", 0)]
    assert not s.waiting


def test_without_ready_sound_the_loop_fades_out(tmp_path):
    s, log = _service(tmp_path, ("waiting_loop.wav",))
    s.start_waiting()
    s.play_ready()
    assert log == [("play", "waiting_loop.wav", -1), ("fadeout",)]


def test_stop_all_before_recording(tmp_path):
    s, log = _service(tmp_path)
    s.start_waiting()
    s.stop_all()
    s.stop_waiting()                        # nothing left to fade
    assert log[-1] == ("stop",) and not s.waiting


def test_missing_files_play_nothing(tmp_path):
    s, log = _service(tmp_path, ())
    s.play_boot(); s.start_waiting(); s.play_ready()
    assert log == [] and s.enabled


def test_sounds_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("SOUNDS", "0")
    s, log = _service(tmp_path)
    s.play_boot(); s.start_waiting()
    assert log == [] and not s.enabled


def test_mp3_and_ogg_are_found(tmp_path):
    s, _ = _service(tmp_path, ("boot.mp3", "waiting_loop.ogg"))
    assert s._sounds["boot"].path == "boot.mp3" and s._sounds["waiting_loop"].path == "waiting_loop.ogg"


# ── prepare_sounds ───────────────────────────────────────────────────────────

def _music(bpm, seconds=20.0, lead_silence=0.0):
    """Clicks on every beat (louder on bar 1 of each 2) over a soft hum."""
    beat = 60.0 / bpm
    audio = np.zeros(int((seconds + lead_silence) * RATE), np.float32)
    t = np.arange(int(0.2 * RATE)) / RATE
    for i in range(int(seconds / beat)):
        start = int((lead_silence + i * beat) * RATE)
        f = 880.0 if i % 8 == 0 else (660.0 if i % 4 == 0 else 440.0)
        tone = np.sin(2 * np.pi * f * t) * np.exp(-12 * t)
        audio[start:start + tone.size] += tone[: audio.size - start]
    return audio


@pytest.mark.parametrize("bpm", [120.0, 116.0, 124.0])
def test_loop_length_follows_the_real_tempo(bpm):
    loop = ps.make_loop(_music(bpm), bpm=120.0, bars=2)
    real = 2 * 4 * 60.0 / bpm
    assert abs(loop.size / RATE - real) < 0.01


def test_loop_join_is_smooth():
    loop = ps.make_loop(_music(120.0))
    jump = abs(float(loop[-1]) - float(loop[0]))
    typical = float(np.mean(np.abs(np.diff(loop)))) * 20
    assert jump <= max(typical, 1e-3)


def test_boot_skips_silence_and_fades():
    audio = _music(120.0, seconds=10, lead_silence=1.5)
    boot = ps.make_boot(audio, seconds=3.0)
    assert boot.size == 3 * RATE
    assert np.max(np.abs(boot[: int(0.05 * RATE)])) > 0.1   # starts on the music, not silence
    assert abs(boot[-1]) < 1e-3                               # faded out


def test_placeholders_and_saved_loudness(tmp_path):
    from scipy.io import wavfile
    sounds = ps.placeholders()
    assert sounds["waiting_loop"].size == 4 * RATE
    for name, audio in sounds.items():
        rate, data = wavfile.read(ps.save(name, audio, tmp_path))
        x = data.astype(np.float32) / 32767
        assert rate == RATE and np.max(np.abs(x)) <= ps.PEAK + 1e-3


def test_buildup_then_loop_with_no_gap(tmp_path):
    s, log = _service(tmp_path, ("waiting_build.wav", "waiting_loop.wav", "ready.wav"))
    s.start_waiting()
    assert log == [("play", "waiting_build.wav", 0), ("queue", "waiting_loop.wav")]
    s.update()                                  # loop still queued: nothing to do
    assert len(log) == 2
    s._channel.queued = None                    # build-up ended, loop started playing
    s.update()
    assert log[-1] == ("queue", "waiting_loop.wav")   # loop queued behind itself
    s.play_ready()
    assert log[-1] == ("play", "ready.wav", 0) and s._channel.queued is None
    s.update()                                  # no longer waiting: no re-queue
    assert log[-1] == ("play", "ready.wav", 0)


def test_fading_out_the_buildup_starts_nothing_after_it(tmp_path):
    s, log = _service(tmp_path, ("waiting_build.wav", "waiting_loop.wav"))
    s.start_waiting()
    s.stop_waiting()
    assert log[-2:] == [("queue", "silence"), ("fadeout",)]   # loop no longer queued
    s.update()
    assert log[-1] == ("fadeout",)


def test_without_buildup_the_loop_repeats_as_before(tmp_path):
    s, log = _service(tmp_path, ("waiting_loop.wav",))
    s.start_waiting(); s.update()
    assert log == [("play", "waiting_loop.wav", -1)]


def test_build_up_file_hands_over_exactly(tmp_path):
    loop = ps.make_loop(_music(120.0), 120.0, 2)
    build = ps.make_buildup(loop, repeats=3)
    n = loop.size
    assert build.size == 3 * n
    tail = n // 2 - 4096                     # after the filter's last frames have passed
    assert np.max(np.abs(build[-tail:] - loop[-tail:])) < 1e-3          # it ends exactly as the loop does
    first = float(np.sqrt(np.mean(build[:n] ** 2))); last = float(np.sqrt(np.mean(build[-n:] ** 2)))
    assert first < 0.75 * last                                        # starts quieter
