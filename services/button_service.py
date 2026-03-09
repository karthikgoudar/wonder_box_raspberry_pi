import threading
import time
import platform

BUTTON_PIN = 13  # Your wiring: GPIO13 → Button → GND (Pin 9)

class ButtonService:
    def __init__(self):
        self._pressed = False
        self._held = False
        self._lock = threading.Lock()
        self._running = True
        self._is_rpi = platform.system() == "Linux"
        self._gpio = None

        if self._is_rpi:
            self._setup_gpio()
            # If using lgpio we start the polling thread; gpiozero uses callbacks.
            if getattr(self, "_use_lgpio", False) and self._gpio is not None:
                threading.Thread(target=self._gpio_loop, daemon=True).start()
        else:
            # Mac/dev mode — silent (no fake input)
            print("[ButtonService] Dev mode (no GPIO)")

    def _setup_gpio(self):
        # Try gpiozero first (high-level), fall back to lgpio low-level
        try:
            from gpiozero import Button as GZButton
            b = GZButton(BUTTON_PIN, pull_up=True, bounce_time=0.15)
            # gpiozero callbacks run in background threads
            b.when_pressed = lambda: self._on_pressed()
            b.when_released = lambda: self._on_released()
            self._gpio = b
            self._use_lgpio = False
            print(f"[ButtonService] gpiozero Button ready on pin {BUTTON_PIN}")
            return
        except Exception:
            pass

        try:
            import lgpio
            self.lgpio = lgpio
            self._gpio = lgpio.gpiochip_open(0)
            # Pull-up because button goes to GND
            lgpio.gpio_claim_input(self._gpio, BUTTON_PIN, lgpio.SET_PULL_UP)
            self._use_lgpio = True
            print(f"[ButtonService] lgpio ready on pin {BUTTON_PIN}")
        except Exception as e:
            print("[ButtonService] GPIO init failed:", e)
            self._gpio = None
            self._use_lgpio = False

    def _on_pressed(self):
        with self._lock:
            self._held = True
            self._pressed = True
        print("[ButtonService] gpiozero: pressed")

    def _on_released(self):
        with self._lock:
            self._held = False
        print("[ButtonService] gpiozero: released")

    def _gpio_loop(self):
        last_state = 1  # pull-up idle = HIGH
        debounce_time = 0.15
        last_press_time = 0

        while self._running:
            try:
                state = self.lgpio.gpio_read(self._gpio, BUTTON_PIN)

                # Detect falling edge (button press)
                if state == 0 and last_state == 1:
                    now = time.time()
                    if now - last_press_time > debounce_time:
                        with self._lock:
                            self._pressed = True
                            self._held = True
                        last_press_time = now
                        print("[ButtonService] Physical button pressed")
                # Detect rising edge (button release)
                if state == 1 and last_state == 0:
                    with self._lock:
                        self._held = False

                last_state = state
                time.sleep(0.01)  # 10ms polling (fast + low CPU)

            except Exception:
                time.sleep(0.1)

    def _set_pressed(self):
        with self._lock:
            self._pressed = True

    def was_pressed(self):
        with self._lock:
            if self._pressed:
                self._pressed = False
                return True
        return False
    
    def is_held(self):
        with self._lock:
            if self._is_rpi and self._gpio is not None:
                try:
                    if getattr(self, "_use_lgpio", False):
                        return self.lgpio.gpio_read(self._gpio, BUTTON_PIN) == 0
                    else:
                        # gpiozero Button exposes is_pressed
                        return bool(self._gpio.is_pressed)
                except Exception:
                    return False
            # Non-RPi: not physically held
            return False

    def cleanup(self):
        self._running = False
        try:
            if self._gpio is not None:
                self.lgpio.gpiochip_close(self._gpio)
        except Exception:
            pass