import time


class PrinterService:
    def __init__(self, duration: float = 3.0):
        self._duration = duration
        self.reset()

    def start_print(self, image):
        """Begin printing an image"""
        self.reset()
        self._image = image
        self._start_time = time.time()
        print("[PRINTER] start_print", flush=True)

    def update(self):
        """Advance printing if needed"""
        if self._start_time is None or self._done:
            return
        elapsed = time.time() - self._start_time
        if not self._progress_logged:
            print("[PRINTER] printing...", flush=True)
            self._progress_logged = True
        if elapsed >= self._duration:
            self._done = True
            print("[PRINTER] done", flush=True)

    def is_done(self) -> bool:
        """True when printing is finished"""
        return self._done

    def has_failed(self) -> bool:
        """True if printing failed"""
        return self._failed

    def get_error(self) -> str | None:
        """Return error message"""
        return self._error

    def reset(self):
        """Clear internal state"""
        self._image = None
        self._start_time = None
        self._done = False
        self._failed = False
        self._error = None
        self._progress_logged = False
