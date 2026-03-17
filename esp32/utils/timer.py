# ============================================================
# utils/timer.py — Simple countdown timer for ESP32
# ============================================================
import utime

class Timer:
    def __init__(self, duration_sec):
        self._duration_ms = int(duration_sec * 1000)
        self._start_ms = None

    def start(self):
        self._start_ms = utime.ticks_ms()

    def reset(self):
        self._start_ms = None

    def is_finished(self):
        if self._start_ms is None:
            return False
        return utime.ticks_diff(utime.ticks_ms(), self._start_ms) >= self._duration_ms

    def elapsed_ms(self):
        if self._start_ms is None:
            return 0
        return utime.ticks_diff(utime.ticks_ms(), self._start_ms)
