import time

class Timer:
    def __init__(self, duration_seconds):
        self.duration = duration_seconds
        self.start_time = None

    def start(self):
        self.start_time = time.time()

    def is_finished(self):
        if self.start_time is None:
            return False
        return (time.time() - self.start_time) >= self.duration
    
    def is_running(self):
        """Check if timer is currently running."""
        return self.start_time is not None and not self.is_finished()
    
    def reset(self):
        """Reset timer to unstarted state."""
        self.start_time = None