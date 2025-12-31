import pygame
from ui.screen_base import Screen

class PrintingScreen(Screen):
    def __init__(self):
        self.font = pygame.font.SysFont(None, 48)

    def render(self, surface):
        surface.fill((30, 30, 30))
        text = self.font.render("Printing...", True, (255, 255, 255))
        rect = text.get_rect(center=surface.get_rect().center)
        surface.blit(text, rect)

import pygame
from ui.screen_base import Screen

class PrintingScreen(Screen):
    def __init__(self):
        self.font = pygame.font.SysFont(None, 48)

    def render(self, surface):
        surface.fill((30, 30, 30))
        text = self.font.render("Printing...", True, (255, 255, 255))
        rect = text.get_rect(center=surface.get_rect().center)
        surface.blit(text, rect)