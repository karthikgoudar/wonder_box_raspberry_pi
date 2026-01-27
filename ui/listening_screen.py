import pygame
from ui.screen_base import Screen

class ListeningScreen(Screen):
    def __init__(self):
        pass

    def handle_event(self, event):
        # Don't consume events - let main.py handle them
        pass

    def render(self, surface):
        surface.fill((255, 255, 255))
        from ui.font import render_text
        render_text(surface, "Listening...", 48, (0, 0, 0), center=True)

