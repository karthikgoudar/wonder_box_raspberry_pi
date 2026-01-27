import pygame
from ui.screen_base import Screen


class IdleScreen(Screen):
    def __init__(self, on_start):
        self.on_start = on_start

    def handle_event(self, event):
        # handle input events
        # Accept multiple input types (Mac, touchscreen, mouse, keyboard)
        if event.type in (
            pygame.MOUSEBUTTONDOWN,  # mouse / physical click
            pygame.FINGERDOWN,       # trackpad / touchscreen
            pygame.KEYDOWN           # keyboard fallback
        ):
            self.on_start()

    def render(self, surface):
        surface.fill((255, 255, 255))

        from ui.font import render_text
        render_text(surface, "Tap to Start", 48, (0, 0, 0), center=True)