"""Turn Gemini music tracks into the app's sounds (assets/sounds/*.wav).

Runs on a Mac with ffmpeg (to read MP3/MP4/WAV).

    venv/bin/python tools/prepare_sounds.py boot  ~/Downloads/boot.mp3
    venv/bin/python tools/prepare_sounds.py loop  ~/Downloads/loop.mp3 --bpm 120 --bars 2
    venv/bin/python tools/prepare_sounds.py ready ~/Downloads/ding.mp3 --seconds 1.2
    venv/bin/python tools/prepare_sounds.py buildup assets/sounds/waiting_loop.wav
    venv/bin/python tools/prepare_sounds.py placeholders   # simple made-up sounds for testing

boot   keeps the first few seconds from where the music starts, with a fade.
loop   finds the real length of `bars` bars near the given tempo, picks the
       start where the end flows best back into the beginning, and blends
       the join so it repeats without a click.
buildup  takes a finished loop and makes waiting_build.wav: the loop played
       a few times, starting quieter and muffled (far away) and opening up to
       full (arriving). Its last bar is the loop untouched and at the same
       loudness, so the app can go straight from the build-up into the loop.
All sounds are evened out to the same loudness and saved as 44.1 kHz WAV.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile

RATE = 44100
OUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "sounds"
TARGET_RMS = {"boot": 0.12, "waiting_loop": 0.07, "ready": 0.12}  # the loop sits quieter
PEAK = 0.89


def decode(path: Path) -> np.ndarray:
    """Any audio/video file -> mono float32 at RATE."""
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed (brew install ffmpeg)")
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(RATE),
         "-f", "f32le", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def level(audio: np.ndarray, rms: float) -> np.ndarray:
    """Scale to a loudness, keeping peaks below PEAK."""
    now = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0
    if now <= 1e-6:
        return audio
    audio = audio * (rms / now)
    peak = float(np.max(np.abs(audio)))
    return audio * (PEAK / peak) if peak > PEAK else audio


def first_sound(audio: np.ndarray, threshold=0.05) -> int:
    """Where the music starts: first sample above `threshold` of the loudest."""
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    hits = np.flatnonzero(np.abs(audio) > threshold * peak) if peak > 0 else np.array([], int)
    return int(hits[0]) if hits.size else 0


def make_boot(audio: np.ndarray, seconds=3.0, fade=0.5) -> np.ndarray:
    start = max(0, first_sound(audio) - int(0.01 * RATE))
    clip = audio[start:start + int(seconds * RATE)].copy()
    n = min(int(fade * RATE), clip.size)
    if n:
        clip[-n:] *= np.linspace(1.0, 0.0, n) ** 2
    attack = min(int(0.005 * RATE), clip.size)
    clip[:attack] *= np.linspace(0.0, 1.0, attack)
    return clip


def _envelope(audio: np.ndarray, hop: int) -> np.ndarray:
    frames = audio[: audio.size // hop * hop].reshape(-1, hop)
    env = np.sqrt(np.mean(frames ** 2, axis=1))
    onset = np.maximum(0.0, np.diff(env, prepend=env[:1]))  # rises = notes and beats
    return onset - onset.mean()


def find_period(audio: np.ndarray, bpm=120.0, bars=2, beats_per_bar=4, search=0.08) -> int:
    """Length of `bars` bars in samples, measured from the music itself
    (the tempo asked for is only a starting guess)."""
    expected = bars * beats_per_bar * 60.0 / bpm
    hop = RATE // 200  # 5 ms
    env = _envelope(audio, hop)
    lo, hi = int(expected * (1 - search) * 200), int(expected * (1 + search) * 200)
    if env.size < hi * 2:
        return int(round(expected * RATE))
    scores = [float(np.dot(env[:-lag], env[lag:])) / (env.size - lag) for lag in range(lo, hi + 1)]
    best = lo + int(np.argmax(scores))
    # refine to the sample around the best 5 ms step
    window = audio[: min(audio.size, int(RATE * 12))]
    centre = best * hop
    cands = range(max(1, centre - hop), centre + hop + 1, 4)
    def match(p):
        a, b = window[:-p], window[p:]
        return float(np.dot(a, b)) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)
    return max(cands, key=match) if window.size > centre + hop else centre


def make_loop(audio: np.ndarray, bpm=120.0, bars=2, skip=4.0, xfade=0.03, period=None) -> np.ndarray:
    """`period` (samples) fixes the loop length; otherwise it is measured.
    Measure on the whole track: a short piece can give a wrong length."""
    period = int(period) if period else find_period(audio, bpm, bars)
    x = int(xfade * RATE)
    first = min(int(skip * RATE), max(0, audio.size - 2 * period - x - 1))
    if audio.size < first + period + x:
        raise ValueError("track too short for one loop")
    # start where the music a loop later sounds most like here (smoothest join)
    w = int(0.05 * RATE)
    best, best_cost = first, None
    for s in range(first, min(first + period, audio.size - period - x - w), int(0.005 * RATE)):
        cost = float(np.mean((audio[s:s + w] - audio[s + period:s + period + w]) ** 2))
        if best_cost is None or cost < best_cost:
            best, best_cost = s, cost
    seg = audio[best:best + period + x].copy()
    loop = seg[:period].copy()
    ramp = np.linspace(0.0, 1.0, x)
    loop[:x] = seg[:x] * ramp + seg[period:period + x] * (1.0 - ramp)  # end flows into start
    return loop


def make_buildup(loop: np.ndarray, repeats=3, start_gain=0.5, start_cut=900.0) -> np.ndarray:
    """The loop `repeats` times, growing louder and brighter until the last
    half loop, which is left exactly as the loop is."""
    from scipy.signal import stft, istft
    n = loop.size
    total = repeats * n
    ramp = (repeats - 0.5) * n / RATE                      # seconds of growing
    x = np.tile(loop, repeats + 1).astype(np.float32)      # extra loop: clean tail
    f, t, Z = stft(x, RATE, nperseg=2048, noverlap=1536)
    k = np.clip(t / ramp, 0, 1)
    cut = start_cut * (20000.0 / start_cut) ** k           # 900 Hz -> fully open
    mask = 1.0 / (1.0 + (f[:, None] / cut[None, :]) ** 4)
    mask[:, k >= 1] = 1.0
    _, y = istft(Z * mask, RATE, nperseg=2048, noverlap=1536)
    y = y[:x.size]
    g = np.clip(np.arange(x.size) / RATE / ramp, 0, 1)
    y = y * (start_gain + (1 - start_gain) * g * g * (3 - 2 * g))
    return y[:total].astype(np.float32)


def chime(freq, length, decay=3.0):
    t = np.arange(int(length * RATE)) / RATE
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(4 * np.pi * freq * t) + 0.1 * np.sin(6 * np.pi * freq * t)
    return (tone * np.exp(-decay * t)).astype(np.float32)


def placeholders():
    """Simple sounds so the app can be tried before the Gemini tracks exist."""
    c, e, g, c2, e2 = 523.25, 659.25, 783.99, 1046.5, 1318.5
    boot = np.zeros(int(2.2 * RATE), np.float32)
    for i, f in enumerate((c, e, g, c2)):
        start = int(i * 0.15 * RATE)
        tone = chime(f, 2.2 - i * 0.15, 2.5)
        boot[start:start + tone.size] += tone
    period = int(4.0 * RATE)  # 2 bars at 120 BPM
    loop = np.zeros(period + RATE, np.float32)
    for i, f in enumerate((c, g, e, g, c2, g, e, g, c, g, e, g, e2, g, e, g)):
        start = int(i * 0.25 * RATE)
        tone = chime(f, 0.6, 9.0) * (1.0 if i % 4 == 0 else 0.6)
        loop[start:start + tone.size] += tone
    loop[:RATE] += loop[period:period + RATE]  # notes ringing past the end continue at the start
    ready = np.zeros(int(1.2 * RATE), np.float32)
    for i, f in enumerate((g, c2)):
        tone = chime(f, 1.2 - i * 0.12, 3.5)
        ready[int(i * 0.12 * RATE):int(i * 0.12 * RATE) + tone.size] += tone
    return {"boot": boot, "waiting_loop": loop[:period], "ready": ready}


def save(name: str, audio: np.ndarray, out_dir: Path = OUT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    audio = level(audio.astype(np.float32), TARGET_RMS[name])
    path = out_dir / f"{name}.wav"
    wavfile.write(path, RATE, (np.clip(audio, -1, 1) * 32767).astype(np.int16))
    print(f"saved {path} ({audio.size / RATE:.2f} s)")
    return path


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("kind", choices=["boot", "loop", "ready", "buildup", "placeholders"])
    p.add_argument("source", nargs="?", type=Path)
    p.add_argument("--seconds", type=float, help="boot/ready length (default 3 / 1.2)")
    p.add_argument("--bpm", type=float, default=120.0)
    p.add_argument("--bars", type=int, default=2)
    p.add_argument("--skip", type=float, default=4.0, help="loop: seconds of the track to skip first")
    p.add_argument("--repeats", type=int, default=3, help="buildup: loop plays this many times while growing")
    p.add_argument("--out", type=Path, default=OUT_DIR)
    a = p.parse_args(argv)
    if a.kind == "placeholders":
        for name, audio in placeholders().items():
            save(name, audio, a.out)
        return
    if a.source is None:
        p.error("give the Gemini file to use")
    if a.kind == "buildup":
        # keep the loop's own loudness so the build-up hands over without a jump
        rate, data = wavfile.read(a.source)
        loop = data.astype(np.float32) / 32767
        build = make_buildup(loop, a.repeats)
        a.out.mkdir(parents=True, exist_ok=True)
        path = a.out / "waiting_build.wav"
        wavfile.write(path, RATE, (np.clip(build, -1, 1) * 32767).astype(np.int16))
        print(f"saved {path} ({build.size / RATE:.2f} s, then {a.source.name} repeats)")
        return
    audio = decode(a.source)
    if a.kind == "boot":
        save("boot", make_boot(audio, a.seconds or 3.0), a.out)
    elif a.kind == "ready":
        save("ready", make_boot(audio, a.seconds or 1.2, fade=0.3), a.out)
    else:
        loop = make_loop(audio, a.bpm, a.bars, a.skip)
        print(f"loop is {loop.size / RATE:.3f} s ({a.bars} bars, about {a.bars * 4 * 60 * RATE / loop.size:.1f} BPM)")
        save("waiting_loop", loop, a.out)


if __name__ == "__main__":
    main()
