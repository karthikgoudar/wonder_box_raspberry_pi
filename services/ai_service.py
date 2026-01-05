"""
AIService: generate one 512x512 PNG via OpenAI Images. Non-blocking for the FSM
by using a background thread; update() is a no-op. Public API remains stable.
"""

import base64
import io
import os
import threading

import pygame
from openai import OpenAI


class AIService:
    def __init__(self):
        self._client = None
        self._prompt = None
        self._image_surface = None
        self._error = None
        self._done = False
        self._failed = False
        self._thread = None
        self._lock = threading.Lock()

        # Graceful disable when API key is missing
        if not os.getenv("OPENAI_API_KEY"):
            self._error = "AI disabled: missing API key"
            self._failed = True
            print("[AI ERROR] missing OPENAI_API_KEY; AI disabled", flush=True)
            return

        self._client = OpenAI()

    # ------------------------
    # Public API (unchanged)
    # ------------------------
    def start_generation(self, prompt: str):
        """Begin image generation; returns immediately."""
        if self._client is None or self._failed:
            # Already disabled; respect prior error state
            print("[AI ERROR] generation skipped (AI disabled)", flush=True)
            return
        self.reset()
        with self._lock:
            self._prompt = self._make_kid_safe_prompt(prompt)
        print("[AI] generation started", flush=True)
        self._thread = threading.Thread(target=self._generate_image, daemon=True)
        self._thread.start()

    def update(self):
        # Non-blocking: work happens in background thread
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

    def get_error(self):
        with self._lock:
            return self._error

    def reset(self):
        with self._lock:
            self._prompt = None
            self._image_surface = None
            self._error = None
            self._done = False
            self._failed = False
        self._thread = None  # in-flight thread may finish; results are ignored

    # ------------------------
    # Internal helpers
    # ------------------------
    def _make_kid_safe_prompt(self, prompt: str) -> str:
        return f"A friendly, colorful, kid-safe illustration: {prompt.strip()}"

    def _generate_image(self):
        try:
            prompt = self._prompt or ""
            response = self._client.images.generate(
                prompt=prompt,
                n=1,
                size="512x512",
                response_format="b64_json",
            )
            b64_data = response.data[0].b64_json
            image_bytes = io.BytesIO(base64.b64decode(b64_data))
            image_bytes.seek(0)
            surface = pygame.image.load(image_bytes, "image.png").convert_alpha()
            with self._lock:
                self._image_surface = surface
                self._done = True
            print("[AI] generation complete", flush=True)
        except Exception as e:
            with self._lock:
                self._error = str(e)
                self._failed = True
            print(f"[AI ERROR] {e}", flush=True)