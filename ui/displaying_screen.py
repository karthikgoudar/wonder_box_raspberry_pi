import pygame
from ui.screen_base import Screen

class DisplayingScreen(Screen):
    def __init__(self, on_approve=None):
        # `on_approve` is optional to avoid instantiation errors
        # when factories or tests don't provide the callback.
        self.on_approve = on_approve
        self.font = pygame.font.SysFont(None, 36)

    def handle_event(self, event):
        if event.type in (
            pygame.MOUSEBUTTONDOWN,
            pygame.FINGERDOWN,
            pygame.KEYDOWN
        ):
            if callable(self.on_approve):
                self.on_approve()

    def render(self, surface):
        surface.fill((20, 40, 60))

        title = self.font.render("Here is your picture!", True, (255, 255, 255))
        approve = self.font.render("Tap to Print", True, (200, 255, 200))

        title_rect = title.get_rect(center=(400, 200))
        approve_rect = approve.get_rect(center=(400, 260))

        surface.blit(title, title_rect)
        surface.blit(approve, approve_rect)