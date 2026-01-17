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
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class AIService:
    def __init__(self):
        self._client = None
        self._prompt = None
        self._image_surface = None
        self._error = None
        self._done = False
        self._failed = False
        self._cancelled = False
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
            self._cancelled = False  # Clear cancel flag for new generation
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
            # Set a flag to signal thread to abort early if possible
            self._cancelled = True
        self._thread = None  # in-flight thread may finish; results are ignored

    # ------------------------
    # Internal helpers
    # ------------------------
    def _make_kid_safe_prompt(self, prompt: str) -> str:
        return f" {prompt.strip()}"

    def _generate_image(self):
        try:
            prompt = self._prompt or ""
            
            # Check if cancelled before expensive API call
            with self._lock:
                if self._cancelled:
                    print("[AI] generation cancelled before API call", flush=True)
                    return
            
            response = self._client.images.generate(
                prompt=prompt,
                n=1,
                size="512x512",
                response_format="b64_json",
            )
            
            # Check if cancelled after API call (before processing)
            with self._lock:
                if self._cancelled:
                    print("[AI] generation cancelled after API call", flush=True)
                    return
            
            b64_data = response.data[0].b64_json
            image_bytes = io.BytesIO(base64.b64decode(b64_data))
            image_bytes.seek(0)
            surface = pygame.image.load(image_bytes, "image.png").convert_alpha()
            
            with self._lock:
                if not self._cancelled:  # Only set result if not cancelled
                    self._image_surface = surface
                    self._done = True
                    print("[AI] generation complete", flush=True)
                else:
                    print("[AI] generation cancelled, discarding result", flush=True)
        except Exception as e:
            with self._lock:
                if not self._cancelled:  # Only set error if not cancelled
                    self._error = str(e)
                    self._failed = True
                    print(f"[AI ERROR] {e}", flush=True)