"""
AIService: generate one 512x512 PNG via OpenAI Images. Non-blocking for the FSM
by using a background thread; update() is a no-op. Public API remains stable.
"""

import base64
import io
import os
import threading
import time

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
            print(f"[AI] prompt: {self._prompt}", flush=True)
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
        wants_text = any(
        keyword in prompt.lower()
        for keyword in ["say", "says", "write", "text", "spell", "quote", "\""]
        )

        text_rule = (
        "- Include the exact text from the description in the image using large cute bubble letters\n"
        "- Only include the required text, nothing else\n"
        if wants_text
        else
        "- No text, letters, numbers, symbols, or watermarks\n"
            )

        return f"""You are an illustration generator for children.

Create a simple black-and-white line art drawing based on the following description.

Rules:
- Output ONLY clean line art
- No colors, minimal shading, minimal gradients, minimal textures
- Use clear, closed outlines
- Minimal details, easy for a child (ages 4–8) to color
{text_rule}
- Center the main subject and make it large
- Friendly, non-scary, child-safe style
- If characters are mentioned, make them cute and expressive
- No posters, no UI, no templates, no graphic design layouts

If the description is unclear or abstract, interpret it in the simplest and most playful way suitable for a child.

If multiple objects are mentioned, include only the most important ones and avoid clutter.

Important!: Black and White images only, no colors!
Description: {prompt.strip()}
"""
    def _generate_image(self):
        try:
            prompt = self._prompt or ""
            
            # Check if cancelled before expensive API call
            with self._lock:
                if self._cancelled:
                    print("[AI] generation cancelled before API call", flush=True)
                    return
            
            response = self._client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                quality="standard",
                size="1024x1024",
                response_format="b64_json"
                #background="auto"
            )
            
            # Check if cancelled after API call (before processing)
            with self._lock:
                if self._cancelled:
                    print("[AI] generation cancelled after API call", flush=True)
                    return
            
            b64_data = response.data[0].b64_json
            image_bytes = io.BytesIO(base64.b64decode(b64_data))

            # Persist the raw PNG bytes to disk for inspection / reuse
            try:
                raw = image_bytes.getvalue()
                saved_path = self._save_image_bytes(raw)
                print(f"[AI] saved generated image to {saved_path}", flush=True)
            except Exception:
                # Don't fail the whole generation if saving is not possible
                print("[AI] warning: failed to save generated image", flush=True)

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

    def _save_image_bytes(self, image_bytes: bytes) -> str:
        """Save PNG bytes to disk under `outputs/` and return the file path."""
        out_dir = os.getenv("AI_IMAGE_OUTPUT_DIR", "outputs")
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception:
            # Best-effort: if directory can't be created, fall back to cwd
            out_dir = os.getcwd()

        filename = f"ai_image_{int(time.time() * 1000)}.png"
        path = os.path.join(out_dir, filename)
        with open(path, "wb") as f:
            f.write(image_bytes)
        return path