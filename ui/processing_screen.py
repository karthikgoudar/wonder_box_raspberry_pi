import pygame
from ui.screen_base import Screen

class ProcessingScreen(Screen):
    def __init__(self):
        self.dots = 0
        self.last_update = 0

    def update(self, dt):
        self.last_update += dt
        if self.last_update > 500:  # ms
            self.dots = (self.dots + 1) % 4
            self.last_update = 0

    def render(self, surface):
        surface.fill((40, 20, 20))
        from ui.font import render_text
        render_text(surface, "Thinking" + "." * self.dots, 48, (255, 255, 255), center=True)