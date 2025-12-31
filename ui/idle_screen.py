import pygame
from ui.screen_base import Screen


class IdleScreen(Screen):
    def __init__(self, on_start):
        self.on_start = on_start
        self.font = pygame.font.SysFont(None, 48)

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
        surface.fill((20, 20, 40))

        # Debug border to confirm rendering
        pygame.draw.rect(
            surface,
            (255, 255, 255),
            surface.get_rect(),
            2
        )

        text = self.font.render("Tap to Start", True, (255, 255, 255))
        rect = text.get_rect(center=surface.get_rect().center)
        surface.blit(text, rect)