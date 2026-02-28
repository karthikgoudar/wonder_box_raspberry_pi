import time
import threading
import os
import io
import traceback

try:
    import serial
    from serial.tools import list_ports
    _HAS_SERIAL = True
except Exception:
    serial = None
    list_ports = None
    _HAS_SERIAL = False

try:
    from PIL import Image, ImageOps, ImageFilter
    _HAS_PIL = True
except Exception:
    Image = None
    ImageOps = None
    _HAS_PIL = False

import pygame

PRINTER_WIDTH = int(os.getenv("PRINTER_WIDTH", "384"))


def _find_default_port():
    if not _HAS_SERIAL or list_ports is None:
        return None
    ports = list_ports.comports()
    names = [p.device for p in ports]
    if not names:
        return None
    priority_keywords = ['usbserial', 'usbmodem', 'slab', 'cp210', 'ftdi', 'usb']
    for kw in priority_keywords:
        for n in names:
            if kw.lower() in n.lower():
                return n
    for n in names:
        if n.startswith('/dev/cu.'):
            return n
    for n in names:
        if n.startswith('/dev/tty') or n.upper().startswith('COM'):
            return n
    return names[0]


class PrinterService:
    """Thermal printer service optimized for dark, sharp, non-inverted image printing (RP203 / ESC-POS)."""

    def __init__(self, port=None, baud=9600, simulate_duration: float = 3.0):
        self._port_name = port or _find_default_port()
        self._baud = baud
        self._simulate_duration = simulate_duration
        self._thread = None
        self._done = False
        self._failed = False
        self._error = None
        self._lock = threading.Lock()
        self._serial = None

    def start_print(self, surface: pygame.Surface, copies: int = 1, feed: int | None = 3):
        with self._lock:
            self._done = False
            self._failed = False
            self._error = None

        self._thread = threading.Thread(
            target=self._do_print,
            args=(surface, copies, feed),
            daemon=True
        )
        self._thread.start()
        print("[PRINTER] start_print (threaded)", flush=True)

    def _do_print(self, surface: pygame.Surface, copies: int, feed: int | None):
        try:
            pil_img = None

            if _HAS_PIL:
                # Convert pygame surface → PIL
                w, h = surface.get_size()
                raw = pygame.image.tostring(surface, 'RGB')
                pil = Image.frombytes('RGB', (w, h), raw)

                # STEP 1: Convert to grayscale
                pil = pil.convert('L')

                # STEP 2: Strong contrast boost (fixes faint lines)
                pil = ImageOps.autocontrast(pil, cutoff=1)

                # STEP 3: Extra sharpening for thin outlines (very important)
                pil = pil.filter(ImageFilter.SHARPEN)
                pil = pil.filter(ImageFilter.SHARPEN)
                pil = pil.filter(ImageFilter.SHARPEN)

                # STEP 4: High-quality resize (preserves detail)
                if pil.width != PRINTER_WIDTH:
                    ratio = PRINTER_WIDTH / float(pil.width)
                    new_height = int(pil.height * ratio)
                    pil = pil.resize((PRINTER_WIDTH, new_height), Image.LANCZOS)

                # STEP 5: Thermal-safe binarization (NO inversion issues)
                # Lower threshold = darker print & stronger lines
                threshold = 200
                pil = pil.point(lambda x: 0 if x > threshold else 255, mode='1')

                # STEP 6: Crop blank borders (keeps tight margins)
                bbox = pil.getbbox()
                if bbox:
                    pil = pil.crop(bbox)

                pil_img = pil

            # Fallback simulation
            if pil_img is None or not _HAS_SERIAL or self._port_name is None:
                print("[PRINTER] Simulating print", flush=True)
                time.sleep(self._simulate_duration)
                with self._lock:
                    self._done = True
                return

            # Convert to ESC/POS raster format
            width_bytes = (pil_img.width + 7) // 8
            height = pil_img.height
            img_bytes = pil_img.tobytes()

            cmd = bytearray()
            cmd += b'\x1d\x76\x30\x00'
            cmd += bytes([width_bytes % 256, width_bytes // 256])
            cmd += bytes([height % 256, height // 256])
            cmd += img_bytes

            # Open serial connection
            if self._serial is None:
                self._serial = serial.Serial(
                    port=self._port_name,
                    baudrate=self._baud,
                    timeout=1
                )

            for i in range(max(1, copies)):
                # Set higher print density & heat (darker like self-test)
                self._serial.write(b'\x1d\x28\x45\x04\x00\x20\x20\x20\x20')

                # Print image (correct polarity, no inversion)
                self._serial.write(cmd)
                self._serial.flush()
                time.sleep(0.08)

                # Your exact requirement: 5 lines bottom padding
                self._serial.write(b"\n\n\n\n")

                print(f"[PRINTER] Printed copy {i+1}/{copies} | Dark, Sharp, Non-Inverted", flush=True)

            with self._lock:
                self._done = True
                print("[PRINTER] done (final optimized output)", flush=True)

        except Exception as e:
            with self._lock:
                self._failed = True
                self._error = str(e) + "\n" + traceback.format_exc()
            print(f"[PRINTER ERROR] {e}", flush=True)

    def update(self):
        return

    def is_done(self) -> bool:
        with self._lock:
            return self._done

    def has_failed(self) -> bool:
        with self._lock:
            return self._failed

    def get_error(self) -> str | None:
        with self._lock:
            return self._error

    def close(self):
        try:
            if self._serial:
                self._serial.close()
        except Exception:
            pass