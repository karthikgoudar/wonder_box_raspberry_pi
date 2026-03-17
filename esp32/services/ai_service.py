# ============================================================
# services/ai_service.py — OpenAI DALL-E Image Generation
# ============================================================
# Sends a text prompt to the OpenAI Images API and retrieves
# the generated image as base64-encoded PNG bytes.
#
# NOTE: This call is BLOCKING (~5-15 seconds) because ESP32
# MicroPython has no threading. The main loop should display
# a "thinking" animation before calling update().
#
# NOTE: ESP32 with PSRAM (≥4 MB) recommended. Standard ESP32
# may run out of RAM on large b64 image payloads.
# Use size "256x256" to reduce memory usage if needed.

import ujson
import ubinascii
import gc
import urequests
from config import OPENAI_API_KEY

# Use smallest size to save RAM; increase if using PSRAM-equipped ESP32
IMAGE_SIZE = "256x256"


class AIService:
    def __init__(self):
        self._prompt      = None
        self._image_bytes = None   # raw PNG bytes
        self._done        = False
        self._failed      = False
        self._error       = None

        if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-YOUR"):
            self._failed = True
            self._error  = "AI disabled: missing API key in config.py"
            print("[AIService ERROR]", self._error)

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def start_generation(self, prompt):
        """Stores prompt and flags for generation on next update() call."""
        if self._failed:
            return
        self.reset()
        self._prompt = self._make_kid_safe_prompt(prompt)
        print("[AIService] prompt ready:", self._prompt[:60], "...")

    def update(self):
        """
        Call every loop. Triggers blocking HTTP request when prompt
        is waiting. Returns immediately if no work to do.
        """
        if self._done or self._failed or self._prompt is None:
            return
        if self._image_bytes is not None:
            return  # already generated

        self._generate_image()

    # --------------------------------------------------------
    # Image generation (blocking)
    # --------------------------------------------------------

    def _generate_image(self):
        prompt = self._prompt
        if not prompt:
            return

        try:
            print("[AIService] calling DALL-E API ...")
            headers = {
                "Authorization": "Bearer " + OPENAI_API_KEY,
                "Content-Type": "application/json",
            }
            body = ujson.dumps({
                "model": "dall-e-2",        # dall-e-2 is cheaper and faster
                "prompt": prompt,
                "n": 1,
                "size": IMAGE_SIZE,
                "response_format": "b64_json",
            })

            resp = urequests.post(
                "https://api.openai.com/v1/images/generations",
                headers=headers,
                data=body,
            )

            if resp.status_code != 200:
                raise RuntimeError("DALL-E API error " + str(resp.status_code) + ": " + resp.text[:100])

            data = ujson.loads(resp.text)
            resp.close()

            b64_str = data["data"][0]["b64_json"]
            # Decode base64 → raw PNG bytes
            self._image_bytes = ubinascii.a2b_base64(b64_str)
            del b64_str
            gc.collect()

            self._done = True
            print("[AIService] image received,", len(self._image_bytes), "bytes")

        except Exception as e:
            self._failed = True
            self._error  = str(e)
            print("[AIService ERROR]", self._error)
            gc.collect()

    # --------------------------------------------------------
    # Kid-safe prompt wrapper (mirrors original logic)
    # --------------------------------------------------------

    def _make_kid_safe_prompt(self, prompt):
        wants_text = any(
            kw in prompt.lower()
            for kw in ("say", "says", "write", "text", "spell", "quote")
        )
        text_rule = (
            "Include the exact text from the description in large cute bubble letters. "
            if wants_text
            else "No text, letters, numbers, symbols, or watermarks. "
        )
        return (
            "Simple black-and-white line art for children ages 4-8 to color. "
            "Clean closed outlines, minimal details, friendly and non-scary. "
            + text_rule
            + "Subject: " + prompt.strip()
        )

    # --------------------------------------------------------
    # Status API
    # --------------------------------------------------------

    def is_done(self):
        return self._done

    def has_failed(self):
        return self._failed

    def get_image_bytes(self):
        """Returns raw PNG bytes or None."""
        return self._image_bytes

    def get_error(self):
        return self._error

    def reset(self):
        self._prompt      = None
        self._image_bytes = None
        self._done        = False
        self._failed      = False
        self._error       = None
        gc.collect()
