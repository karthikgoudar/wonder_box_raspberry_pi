from __future__ import annotations

import time
import threading
import os
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
PRINTER_SIMULATE = os.getenv("PRINTER_SIMULATE", "0").lower() in ("1", "true", "yes")
PRINTER_THRESHOLD = int(os.getenv("PRINTER_THRESHOLD", "200"))
# Pause after each pre-rendered strip so the printer's buffer can drain
PRINTER_STRIP_DELAY = float(os.getenv("PRINTER_STRIP_DELAY", "0.08"))


def _parse_baud_candidates(default_baud: int) -> list[int]:
    raw = os.getenv("PRINTER_BAUD_CANDIDATES", "9600")
    vals: list[int] = []
    for part in raw.split(","):
        p = part.strip()
        if p.isdigit():
            vals.append(int(p))
    if default_baud not in vals:
        vals.insert(0, default_baud)
    # preserve order and deduplicate
    out: list[int] = []
    seen: set[int] = set()
    for v in vals:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _score_port_name(name: str) -> int:
    n = name.lower()
    score = 0
    # Strong signals
    for kw in ("usbserial", "usbmodem", "ttyusb", "ttyacm", "cu.usb", "cp210", "ftdi", "ch340", "serial0", "ttyama"):
        if kw in n:
            score += 30
    # Medium signals
    if "usb" in n:
        score += 10
    # De-prioritize likely non-printer devices
    for bad in ("bluetooth", "debug", "console"):
        if bad in n:
            score -= 20
    return score


def _find_default_port():
    if not _HAS_SERIAL or list_ports is None:
        return None
    names = [p.device for p in list_ports.comports()]
    if not names:
        return None
    ranked = sorted(names, key=_score_port_name, reverse=True)
    return ranked[0]


class PrinterService:
    """Thermal printer service optimized for dark, sharp, non-inverted image printing (RP203 / ESC-POS)."""

    def __init__(self, port=None, baud=9600, simulate_duration: float = 3.0):
        self._port_name = port or os.getenv("PRINTER_PORT") or _find_default_port()
        self._baud = baud
        self._baud_candidates = _parse_baud_candidates(baud)
        self._simulate_duration = simulate_duration
        self._thread = None
        self._done = False
        self._failed = False
        self._error = None
        self._lock = threading.Lock()
        self._serial = None

        print(
            f"[PRINTER] init port={self._port_name} baud={self._baud} "
            f"candidates={self._baud_candidates} simulate={PRINTER_SIMULATE}",
            flush=True,
        )

    def _list_ports(self) -> list[str]:
        if not _HAS_SERIAL or list_ports is None:
            return []
        return [p.device for p in list_ports.comports()]

    def _get_candidate_ports(self) -> list[str]:
        ports = self._list_ports()
        ordered: list[str] = []
        preferred = self._port_name
        if preferred:
            ordered.append(preferred)
        ranked = sorted(ports, key=_score_port_name, reverse=True)
        for p in ranked:
            if p not in ordered:
                ordered.append(p)
        return ordered

    def _is_serial_open(self) -> bool:
        return bool(self._serial is not None and getattr(self._serial, "is_open", False))

    def _open_serial(self):
        if not _HAS_SERIAL:
            raise RuntimeError("pyserial is not installed")

        candidates = self._get_candidate_ports()
        if not candidates:
            raise RuntimeError("No serial printer port found")

        last_error = None
        for port_name in candidates:
            for baud in self._baud_candidates:
                try:
                    ser = serial.Serial(
                        port=port_name,
                        baudrate=baud,
                        timeout=1,
                    )
                    self._serial = ser
                    self._port_name = port_name
                    self._baud = baud
                    print(f"[PRINTER] connected on {port_name} @ {baud}", flush=True)
                    return
                except Exception as e:
                    last_error = e

        available = self._list_ports()
        raise RuntimeError(
            f"Unable to open printer serial port. Tried ports={candidates} bauds={self._baud_candidates}. "
            f"Available now={available}. Last error={last_error}"
        )

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

    def start_print_strips(self, strips, copies: int = 1, feed: int | None = 3):
        """Print a backend-rendered payload: a list of 1,160-byte ESC/POS strips.

        Each strip is a complete GS v 0 command (384px wide, 24 rows), so no
        local image processing is needed. Falls back to nothing here; callers
        use start_print(surface) when the backend sent no payload.
        """
        with self._lock:
            self._done = False
            self._failed = False
            self._error = None

        self._thread = threading.Thread(
            target=self._do_print_strips,
            args=(list(strips), copies, feed),
            daemon=True,
        )
        self._thread.start()
        print(f"[PRINTER] start_print_strips ({len(strips)} strips, threaded)", flush=True)

    def _do_print_strips(self, strips, copies: int, feed: int | None):
        printed = 0
        try:
            if PRINTER_SIMULATE:
                print("[PRINTER] Simulating strip print", flush=True)
                time.sleep(self._simulate_duration)
                with self._lock:
                    self._done = True
                return

            if not _HAS_SERIAL:
                raise RuntimeError("pyserial is not installed; cannot send data to printer")
            if not self._is_serial_open():
                self._open_serial()

            for i in range(max(1, copies)):
                self._serial.write(b"\x1b\x40")  # init
                self._serial.write(b"\x1d\x28\x45\x04\x00\x20\x20\x20\x20")  # density
                for strip in strips:
                    self._serial.write(strip)
                    self._serial.flush()
                    time.sleep(PRINTER_STRIP_DELAY)
                printed += 1
                lines = 4 if feed is None else max(0, int(feed))
                if lines:
                    self._serial.write(b"\n" * lines)
                print(f"[PRINTER] Printed copy {i+1}/{copies} (strips) on {self._port_name}", flush=True)

            with self._lock:
                self._done = True
        except Exception as e:
            if printed > 0 and e.__class__.__name__ == "SerialTimeoutException":
                with self._lock:
                    self._done = True
                return
            with self._lock:
                self._failed = True
                self._error = str(e) + "\n" + traceback.format_exc()
            print(f"[PRINTER ERROR] {e}", flush=True)

    def _do_print(self, surface: pygame.Surface, copies: int, feed: int | None):
        printed_copies = 0
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
                threshold = PRINTER_THRESHOLD
                pil = pil.point(lambda x: 0 if x > threshold else 255, mode='1')

                # STEP 6: Crop blank borders (keeps tight margins)
                bbox = pil.getbbox()
                if bbox:
                    pil = pil.crop(bbox)

                pil_img = pil

            # Optional simulation mode only
            if PRINTER_SIMULATE:
                print("[PRINTER] Simulating print", flush=True)
                time.sleep(self._simulate_duration)
                with self._lock:
                    self._done = True
                return

            if pil_img is None:
                raise RuntimeError("Pillow is not installed; cannot convert image for printing")

            if not _HAS_SERIAL:
                raise RuntimeError("pyserial is not installed; cannot send data to printer")

            # Convert to ESC/POS raster format
            width_bytes = (pil_img.width + 7) // 8
            height = pil_img.height
            img_bytes = pil_img.tobytes()

            cmd = bytearray()
            cmd += b'\x1d\x76\x30\x00'
            cmd += bytes([width_bytes % 256, width_bytes // 256])
            cmd += bytes([height % 256, height // 256])
            cmd += img_bytes

            # Open serial connection (or reconnect if needed)
            if not self._is_serial_open():
                self._open_serial()

            for i in range(max(1, copies)):
                # Initialize printer each job to recover from bad device state
                self._serial.write(b'\x1b\x40')

                # Set higher print density & heat (darker like self-test)
                self._serial.write(b'\x1d\x28\x45\x04\x00\x20\x20\x20\x20')

                # Print image (correct polarity, no inversion)
                self._serial.write(cmd)
                self._serial.flush()
                time.sleep(0.08)
                printed_copies += 1

                # bottom padding
                lines = 4 if feed is None else max(0, int(feed))
                if lines:
                    self._serial.write(b"\n" * lines)

                print(
                    f"[PRINTER] Printed copy {i+1}/{copies} on {self._port_name} @ {self._baud}",
                    flush=True,
                )

            with self._lock:
                self._done = True
                print("[PRINTER] done (final optimized output)", flush=True)

        except Exception as e:
            # If at least one copy is already out, treat write-timeout as non-fatal.
            if printed_copies > 0 and e.__class__.__name__ == "SerialTimeoutException":
                with self._lock:
                    self._done = True
                    self._failed = False
                    self._error = None
                print("[PRINTER] timeout after print output; treated as done", flush=True)
                return

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