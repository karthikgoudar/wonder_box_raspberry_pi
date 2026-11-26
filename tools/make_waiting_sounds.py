"""Make "endless rising" waiting loops (the Shepard tone illusion).

Every note is played in several octaves at once, loudest in the middle.
As the notes climb, the top octave fades out and a new bottom one fades
in, so the sound seems to rise (come closer) forever while the 4-second
file repeats exactly. Bell and marimba-like tones keep it soft for kids.

    venv/bin/python tools/make_waiting_sounds.py [out_dir]

Writes three versions to choose from:
    waiting_rising_plucks.wav   bubbly plucks that keep climbing, soft beat
    waiting_rising_sparkle.wav  the same plus a gentle rising shimmer
    waiting_speeding_up.wav     ticks that keep speeding up, over the shimmer
Copy the chosen one to assets/sounds/waiting_loop.wav.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_sounds as ps  # noqa: E402

RATE = ps.RATE
LOOP = 4.0          # seconds: 2 bars at 120 BPM
CENTRE = 700.0      # Hz where the octaves are loudest (small speakers like 400 Hz+)
SPREAD = 1.1        # octaves either side before fading


def weight(freq):
    """Loudness of one octave copy: highest at CENTRE, fading to nothing far away."""
    return np.exp(-0.5 * (np.log2(np.asarray(freq) / CENTRE) / SPREAD) ** 2)


def bell(freq, length, decay):
    t = np.arange(int(length * RATE)) / RATE
    env = np.exp(-decay * t) * np.minimum(1.0, t / 0.004)  # tiny attack: no click
    tone = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * 2.0 * freq * t) \
        + 0.08 * np.sin(2 * np.pi * 3.0 * freq * t)
    return (tone * env).astype(np.float32)


def _wrap(buf, n):
    """Fold what rings past the loop end back onto the start."""
    out = buf[:n].copy()
    tail = buf[n:]
    out[: tail.size] += tail[: n]
    return out


def rising_plucks(octaves_per_loop=1.0, notes=16, base=130.81):
    """`notes` plucks per loop, each a little higher; one octave per loop."""
    n = int(LOOP * RATE)
    buf = np.zeros(n + RATE, np.float32)
    for i in range(notes):
        pos = (i / notes) * octaves_per_loop % 1.0
        start = int(i * LOOP / notes * RATE)
        accent = 1.0 if i % 4 == 0 else 0.75
        for k in range(7):
            f = base * 2 ** (k + pos)
            w = float(weight(f))
            if w < 0.01:
                continue
            tone = bell(f, 0.7, 7.0) * w * accent
            buf[start:start + tone.size] += tone
    return _wrap(buf, n)


def soft_beat():
    """A gentle wooden 'tok' on each beat (8 per loop), quieter off the bar."""
    n = int(LOOP * RATE)
    buf = np.zeros(n + RATE, np.float32)
    t = np.arange(int(0.12 * RATE)) / RATE
    tok = (np.sin(2 * np.pi * 220 * t) * 0.8 + np.sin(2 * np.pi * 440 * t) * 0.3) * np.exp(-35 * t)
    for i in range(8):
        start = int(i * 0.5 * RATE)
        buf[start:start + tok.size] += tok * (0.6 if i % 4 == 0 else 0.35)
    return _wrap(buf, n)


def shimmer(octaves_per_loop=1.0, base=130.81):
    """A smooth, endlessly rising glide (Shepard-Risset), very soft."""
    n = int(LOOP * RATE)
    x = int(0.05 * RATE)
    t = np.arange(n + x) / RATE
    out = np.zeros(n + x, np.float32)
    for k in range(7):
        f = base * 2 ** (k + octaves_per_loop * t / LOOP)
        phase = 2 * np.pi * np.cumsum(f) / RATE
        out += (np.sin(phase) * weight(f)).astype(np.float32)
    out *= 0.6 + 0.4 * np.sin(2 * np.pi * 4 * t / LOOP) ** 2   # slow sparkle pulse
    loop = out[:n].copy()
    ramp = np.linspace(0, 1, x)
    loop[:x] = out[:x] * ramp + out[n:n + x] * (1 - ramp)       # smooth join
    return loop


def speeding_ticks(layers=4, beats_in_slowest=8, base_pitch=1046.5):
    """Ticks that seem to speed up forever (Risset rhythm): each layer
    doubles in speed over the loop while fading from loud to quiet, and the
    next slower layer fades in to take its place."""
    n = int(LOOP * RATE)
    buf = np.zeros(n + RATE, np.float32)
    f0 = beats_in_slowest * np.log(2) / LOOP        # beats per second at the start
    for j in range(layers):
        count = beats_in_slowest * 2 ** j            # whole beats per loop: seamless
        for b in range(count):
            # time of beat b: phase f0*2^j*L/ln2*(2^(t/L)-1) = b
            t = LOOP * np.log2(1 + b * np.log(2) / (f0 * 2 ** j * LOOP))
            speed = j + t / LOOP                     # in doublings
            w = float(np.exp(-0.5 * ((speed - (layers - 1) / 2) / 0.9) ** 2))
            if w < 0.02:
                continue
            tone = bell(base_pitch * (1.0 if b % 2 == 0 else 1.5), 0.18, 28.0) * w
            start = int(t * RATE)
            buf[start:start + tone.size] += tone
    return _wrap(buf, n)


def main(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    plucks = rising_plucks()
    versions = {
        "waiting_rising_plucks": plucks + 0.5 * soft_beat(),
        "waiting_rising_sparkle": plucks + 0.5 * soft_beat() + 0.35 * shimmer(),
        "waiting_speeding_up": speeding_ticks() + 0.45 * shimmer(),
    }
    for name, audio in versions.items():
        path = ps.save("waiting_loop", audio, out_dir)
        path.rename(out_dir / f"{name}.wav")
        print(f"  -> {name}.wav")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())
