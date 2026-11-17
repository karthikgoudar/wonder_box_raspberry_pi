import pygame
from ui.screen_base import Screen


class ErrorScreen(Screen):
    def __init__(self, callbacks):
        self.callbacks = callbacks
        self.font = None

    def handle_event(self, event):
        # Any interaction resets the system
        if event.type in (
            pygame.MOUSEBUTTONDOWN,
            pygame.FINGERDOWN,
            pygame.KEYDOWN
        ):
            # Safe reset path
            if "reset" in self.callbacks:
                self.callbacks["reset"]()

    def render(self, surface):
        surface.fill((255, 255, 255))
        from ui.font import render_text
        cx, cy = surface.get_rect().center
        from ui.font import ui_scale
        s = ui_scale(surface)
        # Centred on the screen (the old fixed y=220/270 only suited 320x480)
        render_text(surface, "Oops! Something went wrong.", int(40 * s), (200, 0, 0), center=(cx, cy - int(25 * s)))
        render_text(surface, "Tap to start again", int(32 * s), (100, 100, 100), center=(cx, cy + int(25 * s)))