"""
Stand-in for the WonderBox backend, for testing the Pi without AI keys.

Speaks the same contract as the real backend (see services/backend_client.py)
but ignores the audio and always returns the same drawing. Run it on any
machine, then point the Pi's BACKEND_URL at it:

    python tools/fake_backend.py --port 8000 --token test-token

Needs Pillow. The image is 384px wide line art; the print payload is 16
ESC/POS strips of 24 rows, exactly like the real backend produces.
"""

import argparse
import io
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageDraw

W = 384


def make_drawing() -> Image.Image:
    img = Image.new("L", (W, W), 255)
    d = ImageDraw.Draw(img)
    d.ellipse((40, 40, W - 40, W - 40), outline=0, width=8)          # face
    d.ellipse((120, 130, 160, 190), outline=0, width=6)              # eyes
    d.ellipse((224, 130, 264, 190), outline=0, width=6)
    d.arc((100, 150, W - 100, W - 110), 20, 160, fill=0, width=8)    # smile
    d.rectangle((6, 6, W - 7, W - 7), outline=0, width=3)            # frame
    return img


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def print_payload(img: Image.Image) -> bytes:
    """1-bit raster, black = 1, as 24-row GS v 0 strips (1,160 bytes each)."""
    bw = img.convert("L").point(lambda x: 0 if x > 128 else 255, mode="1")
    out = bytearray()
    for y in range(0, bw.height, 24):
        strip = bw.crop((0, y, W, y + 24))
        out += b"\x1d\x76\x30\x00" + bytes([48, 0, 24, 0]) + strip.tobytes()
    return bytes(out)


def make_handler(token: str, delay: float):
    img = make_drawing()
    png, binp = png_bytes(img), print_payload(img)

    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            print("[fake-backend]", fmt % a, flush=True)

        def _send(self, code, body, ctype="application/json"):
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"status": "healthy", "fake": True})
            if self.path == "/storage/fake.png":
                return self._send(200, png, "image/png")
            if self.path == "/storage/fake_print.bin":
                return self._send(200, binp, "application/octet-stream")
            self._send(404, {"detail": "not found"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n)
            if self.headers.get("X-Device-Token") != token:
                return self._send(401, {"detail": "Device credentials required"})
            if self.path.startswith("/sticker/submit"):
                print(f"[fake-backend] got {n} bytes of audio; 'generating' for {delay}s", flush=True)
                time.sleep(delay)
                host = self.headers.get("Host", "localhost")
                return self._send(200, {
                    "status": "done", "job_id": "fake-job", "sticker_id": "fake-1",
                    "text": "a smiley face (fake backend)", "language": "en",
                    "image_url": f"http://{host}/storage/fake.png",
                    "print_url": "/storage/fake_print.bin",
                    "print_png_url": None,
                })
            self._send(404, {"detail": "not found"})

    return H


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--token", default="test-token")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds to pretend to generate")
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(a.token, a.delay))
    print(f"[fake-backend] listening on 0.0.0.0:{a.port} token={a.token!r}", flush=True)
    srv.serve_forever()
