"""Short app sounds: a boot jingle, a loop while a sticker is being made,
and an optional "ready" ding.

Files live in assets/sounds/ (SOUNDS_DIR); each may be .wav, .ogg or .mp3:
    boot          played once when the app starts
    waiting_build played once when the box starts thinking (optional): the
                  loop growing louder and brighter, "getting closer"
    waiting_loop  then repeated until the picture is ready (use .wav or .ogg:
                  MP3s carry hidden silence that leaves a gap every loop)
    ready         played once when the picture appears (optional)
A missing file is simply not played. Make them from Gemini tracks with
tools/prepare_sounds.py.

The build-up hands over to the loop with no gap: the loop is queued behind
it, and update() (called every frame) queues it again each time it starts.

Settings: SOUNDS=0 turns all sounds off; SOUND_VOLUME (0 to 1, default 0.8).

Sounds use their own mixer channel, so they never cut into a story's
narration (which uses pygame.mixer.music).
"""

import os
from pathlib import Path

import pygame

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTS = (".wav", ".ogg", ".mp3")


def sounds_dir() -> Path:
    raw = os.getenv("SOUNDS_DIR")
    return Path(raw).expanduser() if raw else PROJECT_ROOT / "assets" / "sounds"


class SoundService:
    def __init__(self, folder=None, mixer=None):
        self.enabled = os.getenv("SOUNDS", "1").lower() not in ("0", "false", "no")
        self.volume = max(0.0, min(1.0, float(os.getenv("SOUND_VOLUME", "0.8"))))
        self.folder = Path(folder) if folder else sounds_dir()
        self._mixer = mixer or pygame.mixer
        self._sounds = {}
        self._channel = None
        self._silence = None
        self.waiting = False
        self._chaining = False  # build-up playing, loop queued behind it
        if not self.enabled:
            print("[SOUND] off (SOUNDS=0)", flush=True)
            return
        try:
            if not self._mixer.get_init():
                self._mixer.init()
            self._channel = self._mixer.Channel(0)
            self._mixer.set_reserved(1)  # keep channel 0 for these sounds
        except Exception as e:
            print(f"[SOUND] no sound output: {e}", flush=True)
            self.enabled = False
            return
        try:  # queued before a fade-out so nothing queued plays after it
            self._silence = self._mixer.Sound(buffer=bytes(882))
        except Exception:
            self._silence = None
        for name in ("boot", "waiting_build", "waiting_loop", "ready"):
            path = next((self.folder / f"{name}{e}" for e in EXTS if (self.folder / f"{name}{e}").is_file()), None)
            if path is None:
                continue
            try:
                sound = self._mixer.Sound(str(path))
                sound.set_volume(self.volume)
                self._sounds[name] = sound
            except Exception as e:
                print(f"[SOUND] cannot load {path.name}: {e}", flush=True)
        print(f"[SOUND] ready: {', '.join(sorted(self._sounds)) or 'no sound files'} in {self.folder}", flush=True)

    def _play(self, name, loops=0, fade_ms=0):
        sound = self._sounds.get(name)
        if not self.enabled or sound is None or self._channel is None:
            return False
        self._channel.play(sound, loops=loops, fade_ms=fade_ms)
        return True

    def play_boot(self):
        self._play("boot")

    def start_waiting(self):
        """Thinking sound: the build-up once (if there is one), then the loop
        for as long as it takes. Only called after recording has stopped, so
        it never ends up in the microphone."""
        if self.waiting:
            return
        loop = self._sounds.get("waiting_loop")
        if loop is not None and self._play("waiting_build"):
            self._channel.queue(loop)
            self.waiting = self._chaining = True
        else:
            self.waiting = self._play("waiting_loop", loops=-1, fade_ms=150)

    def update(self):
        """Call every frame: keeps the loop queued behind itself after the
        build-up, so it repeats with no gap."""
        if self.waiting and self._chaining and self._channel is not None:
            if self._channel.get_queue() is None:
                self._channel.queue(self._sounds["waiting_loop"])

    def _end_chain(self):
        if self._chaining and self._channel is not None and self._silence is not None:
            self._channel.queue(self._silence)  # a fade-out would start the queued loop
        self._chaining = False

    def stop_waiting(self, fade_ms=250):
        if self.waiting and self._channel is not None:
            self._end_chain()
            self._channel.fadeout(fade_ms)
        self._chaining = False
        self.waiting = False

    def play_ready(self):
        """Sound when the picture appears; it replaces the loop on the channel."""
        if self._play("ready"):
            self._chaining = False  # play() clears anything queued
        else:
            self.stop_waiting()
        self.waiting = False

    def stop_all(self):
        """Silence before recording starts, so no app sound is recorded."""
        if self._channel is not None:
            self._channel.stop()     # stop() does not start anything queued
        self._chaining = False
        self.waiting = False
