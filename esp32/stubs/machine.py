# stubs/machine.py — MicroPython machine → PC hardware stubs
# Pin   → reads pygame mouse/keyboard for the button pin
# I2S   → captures audio via sounddevice (PC microphone)
# UART  → simulates printer output to console / file
# SPI   → no-op (display handled separately by ili9341 stub)

import threading

# ── Pin constants ──────────────────────────────────────────
IN      = 0
OUT     = 1
PULL_UP = 1
PULL_DOWN = 2

class Pin:
    """
    GPIO pin stub.
    For the button pin (PULL_UP), reads pygame keyboard / mouse state.
    SPACE key or left mouse button held → pin LOW (0) = pressed.
    """
    def __init__(self, pin_num, mode=IN, pull=None):
        self._num  = pin_num
        self._mode = mode
        self._pull = pull
        self._out_val = 0

    def value(self, v=None):
        if v is not None:
            self._out_val = v
            return
        if self._pull == PULL_UP:
            # Button pin: LOW = pressed
            try:
                import pygame
                keys  = pygame.key.get_pressed()
                mouse = pygame.mouse.get_pressed()
                if keys[pygame.K_SPACE] or mouse[0]:
                    return 0   # pressed
            except Exception:
                pass
            return 1  # not pressed
        return self._out_val

    def __call__(self, v=None):
        return self.value(v)


# ── I2S ───────────────────────────────────────────────────
class I2S:
    """
    I2S stub — captures audio from the PC default microphone via sounddevice.
    readinto() fills the caller's buffer from an internal ring buffer that is
    continuously written to by a sounddevice background thread.
    """
    RX   = 0
    TX   = 1
    MONO = 0

    def __init__(self, id, sck, ws, sd, mode, bits, format, rate, ibuf):
        self._rate   = rate
        self._buf    = bytearray()
        self._lock   = threading.Lock()
        self._stream = None

        if mode == I2S.RX:
            try:
                import sounddevice as _sd

                def _cb(indata, frames, t, status):
                    with self._lock:
                        self._buf.extend(bytes(indata))

                self._stream = _sd.RawInputStream(
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                    callback=_cb,
                    blocksize=512,
                )
                self._stream.start()
                print("[machine.I2S STUB] sounddevice mic started at", rate, "Hz")
                print("[machine.I2S STUB] SPEAK into your PC microphone now!")
            except ImportError:
                print("[machine.I2S STUB] sounddevice not installed — mic unavailable")
            except Exception as e:
                print("[machine.I2S STUB] could not open mic:", e)

    def readinto(self, buf):
        with self._lock:
            n = min(len(buf), len(self._buf))
            if n > 0:
                buf[:n] = self._buf[:n]
                self._buf = self._buf[n:]
        return n

    def deinit(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        print("[machine.I2S STUB] deinit")


# ── UART ──────────────────────────────────────────────────
class UART:
    """
    UART stub — simulates the thermal printer by logging output to console
    and optionally writing raw bytes to a file 'sim_printer_output.bin'.
    """
    def __init__(self, id, baudrate=9600, tx=None, rx=None):
        self._id = id
        print(f"[machine.UART STUB] init id={id} baud={baudrate}")
        self._file = open("sim_printer_output.bin", "wb")

    def write(self, data):
        if isinstance(data, (bytes, bytearray, memoryview)):
            self._file.write(data)
            self._file.flush()
            print(f"[machine.UART STUB] {len(data)} bytes sent to printer")
        else:
            self._file.write(data.encode() if hasattr(data, "encode") else bytes(data))
        return len(data)

    def read(self, n=-1):
        return b""


# ── SPI ───────────────────────────────────────────────────
class SPI:
    """SPI stub — display is handled entirely by the ili9341 stub via pygame."""
    def __init__(self, id, baudrate=None, sck=None, mosi=None, miso=None):
        pass
