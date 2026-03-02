import threading
import time
import platform

BUTTON_PIN = 13  # Your wiring: GPIO13 → Button → GND (Pin 9)

class ButtonService:
    def __init__(self):
        self._pressed = False
        self._lock = threading.Lock()
        self._running = True
        self._is_rpi = platform.system() == "Linux"
        self._gpio = None

        if self._is_rpi:
            self._setup_gpio()
            if self._gpio is not None:
                threading.Thread(target=self._gpio_loop, daemon=True).start()
        else:
            # Mac/dev mode — silent (no fake input)
            print("[ButtonService] Dev mode (no GPIO)")

    def _setup_gpio(self):
        try:
            import lgpio
            self.lgpio = lgpio
            self._gpio = lgpio.gpiochip_open(0)
            # Pull-up because button goes to GND
            lgpio.gpio_claim_input(self._gpio, BUTTON_PIN, lgpio.SET_PULL_UP)
            print(f"[ButtonService] GPIO ready on pin {BUTTON_PIN}")
        except Exception as e:
            print("[ButtonService] GPIO init failed:", e)
            self._gpio = None

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
                        self._set_pressed()
                        last_press_time = now
                        print("[ButtonService] Physical button pressed")

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
        if not self._is_rpi or self._gpio is None:
            return False
        try:
            return self.lgpio.gpio_read(self._gpio, BUTTON_PIN) == 0
        except Exception:
            return False

    def cleanup(self):
        self._running = False
        try:
            if self._gpio is not None:
                self.lgpio.gpiochip_close(self._gpio)
        except Exception:
            pass