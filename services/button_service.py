import threading
import time
import platform
import os

# Use BCM numbering: your wiring is GPIO27 (BCM) → Button → GND (physical pin 13 → GND pin 9)
BUTTON_PIN = int(os.getenv("BUTTON_PIN", "27"))

class ButtonService:
    def __init__(self):
        self._pressed = False
        self._held = False
        self._lock = threading.Lock()
        self._running = True
        self._is_rpi = platform.system() == "Linux" or os.getenv("FORCE_RPI_BUTTON", "0").lower() in ("1", "true", "yes")
        self._gpio = None
        self._backend = None
        self._rpi_gpio = None
        self._use_lgpio = False

        if self._is_rpi:
            self._setup_gpio()
            # Diagnostic summary
            print(
                f"[ButtonService] init: is_rpi={self._is_rpi} backend={self._backend} gpio_set={self._gpio is not None or self._rpi_gpio is not None} pin={BUTTON_PIN}",
                flush=True,
            )
        else:
            print("[ButtonService] Dev mode (no GPIO)")

    def _setup_gpio(self):
        # 1) Try gpiozero (preferred)
        try:
            from gpiozero import Button as GZButton
            b = GZButton(BUTTON_PIN, pull_up=True, bounce_time=0.05)
            b.when_pressed = lambda: self._on_pressed()
            b.when_released = lambda: self._on_released()
            self._gpio = b
            self._backend = "gpiozero"
            print(f"[ButtonService] gpiozero ready on pin {BUTTON_PIN}", flush=True)
            return
        except Exception as e:
            print(f"[ButtonService] gpiozero not available: {e}", flush=True)

        # 2) Try RPi.GPIO (polling)
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self._rpi_gpio = GPIO
            self._backend = "RPi.GPIO"
            threading.Thread(target=self._rpi_poll_loop, daemon=True).start()
            print(f"[ButtonService] RPi.GPIO polling started on pin {BUTTON_PIN}", flush=True)
            return
        except Exception as e:
            print(f"[ButtonService] RPi.GPIO not available: {e}", flush=True)

        # 3) Try lgpio (low-level) — be defensive: import may succeed but chip init can fail
        try:
            import lgpio
            self.lgpio = lgpio
            self._backend = "lgpio"
            try:
                # Try to open the gpiochip and claim input. If this fails, we will
                # still start the poll thread which will retry initialization.
                handle = lgpio.gpiochip_open(0)
                try:
                    lgpio.gpio_claim_input(handle, lgpio.SET_PULL_UP, BUTTON_PIN)
                except TypeError:
                    lgpio.gpio_claim_input(handle, BUTTON_PIN, lgpio.SET_PULL_UP)
                self._gpio = handle
                self._use_lgpio = True
                threading.Thread(target=self._gpio_loop, daemon=True).start()
                print(f"[ButtonService] lgpio ready on pin {BUTTON_PIN}", flush=True)
                return
            except Exception as inner_e:
                # Initialization failed but lgpio is present — start poll thread to retry.
                print(f"[ButtonService] lgpio present but init failed: {inner_e}; will retry in background",
                      flush=True)
                self._gpio = None
                self._use_lgpio = True
                threading.Thread(target=self._gpio_loop, daemon=True).start()
                return
        except Exception as e:
            # lgpio import failed
            print(f"[ButtonService] lgpio not available: {e}", flush=True)

        # No backend succeeded
        if self._backend is None:
            print(
                "[ButtonService] no GPIO backend available. Button input disabled. "
                "Install gpiozero, RPi.GPIO, or lgpio, or set FORCE_RPI_BUTTON=0 to run in dev mode.",
                flush=True,
            )
            self._gpio = None
            self._use_lgpio = False
            self._backend = "none"

    def _on_pressed(self):
        with self._lock:
            self._held = True
            self._pressed = True
        print(f"[ButtonService] ({self._backend}) pressed", flush=True)

    def _on_released(self):
        with self._lock:
            self._held = False
        print(f"[ButtonService] ({self._backend}) released", flush=True)

    def _gpio_loop(self):
        # lgpio polling loop
        last_state = 1
        debounce_time = 0.05
        last_press_time = 0
        while self._running:
            try:
                state = self.lgpio.gpio_read(self._gpio, BUTTON_PIN)
                if state == 0 and last_state == 1:
                    now = time.time()
                    if now - last_press_time > debounce_time:
                        with self._lock:
                            self._pressed = True
                            self._held = True
                        last_press_time = now
                        print("[ButtonService] (lgpio) Physical button pressed", flush=True)
                if state == 1 and last_state == 0:
                    with self._lock:
                        self._held = False
                last_state = state
                time.sleep(0.01)
            except Exception:
                time.sleep(0.1)

    def _rpi_poll_loop(self):
        # RPi.GPIO polling loop
        last_state = 1
        debounce_time = 0.05
        last_press_time = 0
        GPIO = self._rpi_gpio
        while self._running:
            try:
                state = GPIO.input(BUTTON_PIN)
                if state == 0 and last_state == 1:
                    now = time.time()
                    if now - last_press_time > debounce_time:
                        with self._lock:
                            self._pressed = True
                            self._held = True
                        last_press_time = now
                        print("[ButtonService] (RPi.GPIO) Physical button pressed", flush=True)
                if state == 1 and last_state == 0:
                    with self._lock:
                        self._held = False
                last_state = state
                time.sleep(0.01)
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
            if self._is_rpi:
                try:
                    if self._backend == "gpiozero" and self._gpio is not None:
                        return bool(self._gpio.is_pressed)
                    if self._backend == "RPi.GPIO" and self._rpi_gpio is not None:
                        return self._rpi_gpio.input(BUTTON_PIN) == 0
                    if getattr(self, "_use_lgpio", False):
                        return self.lgpio.gpio_read(self._gpio, BUTTON_PIN) == 0
                except Exception:
                    return False
            return False

    def cleanup(self):
        self._running = False
        try:
            if getattr(self, "_rpi_gpio", None) is not None:
                try:
                    self._rpi_gpio.cleanup()
                except Exception:
                    pass
            if getattr(self, "lgpio", None) is not None and self._gpio is not None:
                try:
                    self.lgpio.gpiochip_close(self._gpio)
                except Exception:
                    pass
        except Exception:
            pass