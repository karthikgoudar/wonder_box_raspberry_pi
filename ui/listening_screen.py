import pygame
from ui.screen_base import Screen

class ListeningScreen(Screen):
    def __init__(self):
        self.font = pygame.font.SysFont(None, 48)

    def render(self, surface):
        surface.fill((10, 40, 20))
        text = self.font.render("Listening...", True, (255, 255, 255))
        rect = text.get_rect(center=surface.get_rect().center)
        surface.blit(text, rect)

