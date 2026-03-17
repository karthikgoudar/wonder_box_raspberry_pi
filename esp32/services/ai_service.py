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
                "model": "dall-e-2",
                "prompt": prompt,
                "n": 1,
                "size": IMAGE_SIZE,
                "response_format": "url",
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
            gc.collect()  # ← free resp immediately

            image_url = data["data"][0]["url"]
            print("[AIService] image URL:", image_url)

            # ← removed: del b64_str  (that variable doesn't exist anymore)

            self._image_bytes = self._fetch_image_chunked(image_url)
            gc.collect()

            self._done = True
            print("[AIService] image received,", len(self._image_bytes), "bytes")

        except Exception as e:
            self._failed = True
            self._error  = str(e)
            print("[AIService ERROR]", self._error)
            gc.collect()


    def _fetch_image_chunked(self, url):
        resp = urequests.get(url)

        if resp.status_code != 200:
            resp.close()
            raise ValueError("HTTP error: " + str(resp.status_code))

        buf = bytearray()
        chunk_size = 4096

        try:
            while True:
                chunk = resp._r.read(chunk_size)
                if not chunk:
                    break
                buf.extend(chunk)
                gc.collect()
        finally:
            resp.close()

        return bytes(buf)  
    
    #this is complex code
    def _fetch_image_chunked_usocket(self, url):
        import usocket
        import ussl
        
        # Parse URL manually
        # url looks like: https://oaidalleapiprodscus.blob.core.windows.net/...
        proto, _, host, path = url.split('/', 3)
        path = '/' + path
        
        # Open raw SSL socket
        addr = usocket.getaddrinfo(host, 443)[0][-1]
        sock = usocket.socket()
        sock.connect(addr)
        sock = ussl.wrap_socket(sock, server_hostname=host)
        
        # Send HTTP GET manually
        request = (
            "GET {} HTTP/1.0\r\n"
            "Host: {}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).format(path, host)
        sock.write(request.encode())
        
        # Skip HTTP headers
        while True:
            line = sock.readline()
            if line in (b'\r\n', b''):
                break
        
        # Read body in chunks
        buf = bytearray()
        chunk = bytearray(4096)
        while True:
            n = sock.readinto(chunk)
            if not n:
                break
            buf.extend(chunk[:n])
            gc.collect()
        
        sock.close()
        return bytes(buf)
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
