import pygame
from ui.screen_base import Screen

class ListeningScreen(Screen):
    def __init__(self):
        pass

    def render(self, surface):
        surface.fill((10, 40, 20))
        from ui.font import render_text
        render_text(surface, "Listening...", 48, (255, 255, 255), center=True)

