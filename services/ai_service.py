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
    get_story_language()         set when the child asked for a story (en/kn/hi)
    reset()                      abandon any in-flight job
"""

import io
import os
import threading

import pygame
from dotenv import load_dotenv

from services.backend_client import BackendClient, BackendError, StickerResult

load_dotenv()


class AIService:
    def __init__(self, client=None):
        self._client = client
        self._image_surface = None
        self._strips = None
        self._text = None
        self._error = None
        self._error_code = None  # backend code, e.g. LANGUAGE_NOT_SUPPORTED
        self._story_language = None
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

    def get_error_code(self):
        """The backend's error code for the last failure, or None."""
        with self._lock:
            return self._error_code

    def get_story_language(self):
        """Language of a story request ("en", "kn", "hi"), or None for a picture."""
        with self._lock:
            return self._story_language

    def fail(self, code, message):
        """Mark the current job failed (e.g. a story was asked for but none is stored)."""
        with self._lock:
            self._error, self._error_code, self._failed = message, code, True

    def reset(self):
        with self._lock:
            self._generation += 1
            self._image_surface = None
            self._strips = None
            self._text = None
            self._story_language = None
            self._done = False
            # A disabled service (no config) stays failed with its reason.
            if self._client is not None:
                self._error = None
                self._error_code = None
                self._failed = False
        self._thread = None  # in-flight thread may finish; its result is dropped

    # ------------------------
    # Internals
    # ------------------------
    def _current(self, gen):
        with self._lock:
            return gen == self._generation

    def _use_stream(self) -> bool:
        """Stream mode sends the spoken words as soon as speech-to-text is
        done (about 1 s), so the thinking screen can show them while the
        picture is made. AI_BACKEND_MODE=direct waits for everything at once."""
        mode = (os.getenv("AI_BACKEND_MODE") or "stream").strip().lower()
        return mode != "direct" and hasattr(self._client, "submit_sticker_stream")

    def _submit_stream(self, wav_path: str, gen: int) -> StickerResult:
        """Follow the backend's step-by-step events; publish the text early."""
        job_id, text, language, urls = "", None, None, {}
        for event, data in self._client.submit_sticker_stream(wav_path):
            if event == "job":
                job_id = data.get("job_id", "")
            elif event == "text":
                text, language = data.get("text"), data.get("language")
                with self._lock:
                    if gen == self._generation:
                        self._text = text  # thinking screen shows it now
                print(f"[AI] heard: {text!r}", flush=True)
            elif event in ("image_ready", "done"):
                urls.update({k: v for k, v in data.items() if v})
        return StickerResult(
            intent=urls.get("intent") or "sticker",
            job_id=job_id,
            sticker_id=urls.get("sticker_id"),
            text=text,
            language=urls.get("language") or language,
            image_url=urls.get("image_url"),
            print_url=urls.get("print_url"),
            print_png_url=urls.get("print_png_url"),
        )

    def _run(self, wav_path: str, gen: int):
        try:
            if self._use_stream():
                result = self._submit_stream(wav_path, gen)
            else:
                result = self._client.submit_sticker(wav_path)
            if not self._current(gen):
                print("[AI] job cancelled; discarding result", flush=True)
                return

            if result.intent == "story":
                with self._lock:
                    if gen != self._generation:
                        return
                    self._story_language = result.language or "en"
                    self._text = result.text
                    self._done = True
                print(f"[AI] story requested ({self._story_language}): {result.text!r}", flush=True)
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
                self._error_code = getattr(e, "code", None)
                self._failed = True
            print(f"[AI ERROR] {e}", flush=True)
