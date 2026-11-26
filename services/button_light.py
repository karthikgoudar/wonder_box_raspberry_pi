"""The arcade button's light: on means "press me".

Wiring (the GPIO pin cannot power the button's LED by itself):
GPIO17 -> 1 kOhm -> base of an NPN transistor (BC547 or 2N2222);
emitter -> GND; collector -> LED minus; LED plus -> 5 V (for a 5 V LED
button; a 12 V LED button needs a 12 V supply on LED plus instead).

BUTTON_LED_PIN picks the pin (default 17); set it empty to turn the light off.
"""

import os

from core.states import State

# What the light does in each state
PATTERNS = {
    State.IDLE: "on",          # waiting for a child: press me
    State.LISTENING: "on",     # held while speaking
    State.PROCESSING: "pulse", # thinking
    State.DISPLAYING: "off",
    State.PRINTING: "off",
    State.STORY: "off",        # presses are ignored during a story
    State.ERROR: "on",         # press to try again
}


class ButtonLight:
    def __init__(self, led=None):
        self._led = led
        self.pattern = None
        if self._led is None:
            pin = (os.getenv("BUTTON_LED_PIN", "17") or "").strip()
            if pin:
                try:
                    from gpiozero import PWMLED
                    self._led = PWMLED(int(pin))
                    print(f"[LIGHT] button light on GPIO{pin}", flush=True)
                except Exception as e:  # not a Pi, or the pin is busy
                    print(f"[LIGHT] button light unavailable: {e}", flush=True)

    def show(self, state):
        pattern = PATTERNS.get(state, "off")
        if pattern == self.pattern or self._led is None:
            self.pattern = pattern
            return
        self.pattern = pattern
        try:
            if pattern == "on":
                self._led.on()
            elif pattern == "pulse":
                self._led.pulse(fade_in_time=0.6, fade_out_time=0.6)
            else:
                self._led.off()
        except Exception as e:
            print(f"[LIGHT] {e}", flush=True)
