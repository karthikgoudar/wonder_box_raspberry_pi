import pygame
from ui.screen_base import Screen
from ui.current_image import get_image


class DisplayingScreen(Screen):
    def __init__(self, approve_print=None):
        # Displaying draws the current image and a small print prompt/button
        self._approve_print = approve_print
        self._button_rect = None

    def handle_event(self, event):
        # Allow clicking the print prompt to move to PRINTING
        try:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                if self._button_rect and self._button_rect.collidepoint(pos):
                    if callable(self._approve_print):
                        self._approve_print()
        except Exception:
            # Ignore harmless event-handling errors
            pass

    def render(self, surface):
        # If a generated image exists, blit it to the screen and keep it
        img = get_image()
        if img:
            # scale to fit while preserving aspect if needed
            img_rect = img.get_rect()
            target_rect = surface.get_rect()
            if img_rect.size != target_rect.size:
                scaled = pygame.transform.smoothscale(img, target_rect.size)
                surface.blit(scaled, (0, 0))
            else:
                surface.blit(img, (0, 0))
        else:
            # fallback blank background when no image is available
            surface.fill((20, 40, 60))
            from ui.font import render_text
            render_text(surface, "Here is your picture!", 36, (255, 255, 255), center=True)
        # Render a small prompt/button at the bottom-center
        from ui.font import render_text
        # Removed prompt text and its rendering
        # Removed prompt rendering and related background/button code