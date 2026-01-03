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
        surface.fill((80, 20, 20))
        from ui.font import render_text
        cx, cy = surface.get_rect().center
        render_text(surface, "Oops! Something went wrong.", 40, (255, 255, 255), center=(cx, 220))
        render_text(surface, "Tap to start again", 32, (200, 200, 200), center=(cx, 270))