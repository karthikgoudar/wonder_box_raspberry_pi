import pygame
from ui.screen_base import Screen

class ProcessingScreen(Screen):
    def __init__(self):
        self.font = pygame.font.SysFont(None, 48)
        self.dots = 0
        self.last_update = 0

    def update(self, dt):
        self.last_update += dt
        if self.last_update > 500:  # ms
            self.dots = (self.dots + 1) % 4
            self.last_update = 0

    def render(self, surface):
        surface.fill((40, 20, 20))
        text = self.font.render(
            "Thinking" + "." * self.dots,
            True,
            (255, 255, 255)
        )
        rect = text.get_rect(center=surface.get_rect().center)
        surface.blit(text, rect)