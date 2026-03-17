# ============================================================
# services/button_service.py — GPIO Button for ESP32
# ============================================================
# Uses machine.Pin with an internal pull-up.
# Button wiring: GPIO_PIN → Button → GND
# Pressed = pin reads LOW (0).

from machine import Pin
import utime
from config import BUTTON_PIN

class ButtonService:
    DEBOUNCE_MS = 150

    def __init__(self):
        self._pin = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self._held = False
        self._last_change_ms = 0
        print("[ButtonService] ready on GPIO", BUTTON_PIN)

    def update(self):
        """
        Call this every main-loop iteration to poll and debounce.
        Returns a tuple (pressed_edge, released_edge).
        pressed_edge  = True on the tick the button is first pressed.
        released_edge = True on the tick the button is first released.
        """
        now = utime.ticks_ms()
        raw = self._pin.value()          # LOW (0) when button is pressed
        current_held = (raw == 0)

        pressed_edge  = False
        released_edge = False

        if current_held != self._held:
            # Only accept the change after debounce interval
            if utime.ticks_diff(now, self._last_change_ms) >= self.DEBOUNCE_MS:
                self._last_change_ms = now
                if current_held:
                    pressed_edge = True
                    print("[ButtonService] pressed")
                else:
                    released_edge = True
                    print("[ButtonService] released")
                self._held = current_held

        return pressed_edge, released_edge

    def is_held(self):
        return self._held
