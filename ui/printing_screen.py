from ui.screen_base import Screen
from ui.displaying_screen import DisplayingScreen


class PrintingScreen(Screen):
    def __init__(self):
        # Delegate rendering to DisplayingScreen so the same image is shown
        self._delegate = DisplayingScreen()

    def handle_event(self, event):
        # Printing should not accept input that alters the image
        pass

    def update(self, dt):
        # Delegate any update (none currently)
        if hasattr(self._delegate, 'update'):
            self._delegate.update(dt)

    def render(self, surface):
        # Render exactly as DISPLAYING does (no 'Printing...' text)
        self._delegate.render(surface)