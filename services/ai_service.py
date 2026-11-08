"""
AIService: turn a recorded WAV into a sticker via the WonderBox cloud backend.

The backend does speech-to-text, prompt building and image generation, and
returns a display image plus a pre-rendered thermal print payload. The Pi no
longer holds an OpenAI key. Work runs on a background thread so the pygame
loop never blocks; update() is a no-op.

Public API (used by main.py):
    start_generation(wav_path)   begin; returns immediately
    is_done() / has_failed() / get_error()
    get_image()                  pygame.Surface for the LCD
    get_print_strips()           list of 1,160-byte ESC/POS strips, or None
    get_text()                   what the child said, as transcribed
    reset()                      abandon any in-flight job
"""

import io
import threading

import pygame
from dotenv import load_dotenv

from services.backend_client import BackendClient, BackendError

load_dotenv()


class AIService:
    def __init__(self, client=None):
        self._client = client
        self._image_surface = None
        self._strips = None
        self._text = None
        self._error = None
        self._done = False
        self._failed = False
        self._generation = 0  # bumped by reset(); stale threads discard results
        self._thread = None
        self._lock = threading.Lock()

        if self._client is None:
            try:
                self._client = BackendClient()
            except ValueError as e:
                # Missing BACKEND_URL / DEVICE_TOKEN: stay up, fail on use.
                self._error = f"AI disabled: {e}"
                self._failed = True
                print(f"[AI ERROR] {self._error}", flush=True)

    # ------------------------
    # Public API
    # ------------------------
    def start_generation(self, wav_path: str):
        """Begin sticker generation from a WAV file; returns immediately."""
        if self._client is None:
            print("[AI ERROR] generation skipped (AI disabled)", flush=True)
            return
        self.reset()
        with self._lock:
            gen = self._generation
        print(f"[AI] submitting {wav_path} to backend", flush=True)
        self._thread = threading.Thread(
            target=self._run, args=(wav_path, gen), daemon=True
        )
        self._thread.start()

    def update(self):
        return

    def is_done(self):
        with self._lock:
            return self._done

    def has_failed(self):
        with self._lock:
            return self._failed

    def get_image(self):
        with self._lock:
            return self._image_surface

    def get_print_strips(self):
        with self._lock:
            return self._strips

    def get_text(self):
        with self._lock:
            return self._text

    def get_error(self):
        with self._lock:
            return self._error

    def reset(self):
        with self._lock:
            self._generation += 1
            self._image_surface = None
            self._strips = None
            self._text = None
            self._done = False
            # A disabled service (no config) stays failed with its reason.
            if self._client is not None:
                self._error = None
                self._failed = False
        self._thread = None  # in-flight thread may finish; its result is dropped

    # ------------------------
    # Internals
    # ------------------------
    def _current(self, gen):
        with self._lock:
            return gen == self._generation

    def _run(self, wav_path: str, gen: int):
        try:
            result = self._client.submit_sticker(wav_path)
            if not self._current(gen):
                print("[AI] job cancelled; discarding result", flush=True)
                return

            if not result.image_url:
                raise BackendError("backend returned no image_url")
            png = self._client.download(result.image_url)
            surface = pygame.image.load(io.BytesIO(png), "image.png").convert_alpha()

            # The print payload is best-effort here: if it fails we still show
            # the image and the printer falls back to local rasterising.
            strips = None
            if result.print_url:
                try:
                    strips = self._client.download_print_strips(result.print_url)
                except BackendError as e:
                    print(f"[AI] print payload unavailable ({e}); will use fallback", flush=True)

            with self._lock:
                if gen != self._generation:
                    return
                self._image_surface = surface
                self._strips = strips
                self._text = result.text
                self._done = True
            print(f"[AI] sticker ready: {result.text!r}", flush=True)
        except Exception as e:
            with self._lock:
                if gen != self._generation:
                    return
                self._error = str(e)
                self._failed = True
            print(f"[AI ERROR] {e}", flush=True)
