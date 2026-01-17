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
        prompt = "Tap to print — click here to print"
        text_surf, text_rect = render_text(surface, prompt, 24, (255, 255, 255), center=False)
        # place bottom-center with some padding
        sw = surface.get_width()
        sh = surface.get_height()
        padding = 16
        text_rect.centerx = sw // 2
        text_rect.bottom = sh - padding

        # Draw a subtle rounded rectangle behind the text
        bg_rect = text_rect.inflate(24, 12)
        try:
            pygame.draw.rect(surface, (0, 0, 0, 160), bg_rect, border_radius=8)
        except Exception:
            # Some pygame builds may not support alpha in draw.rect background; use solid
            pygame.draw.rect(surface, (0, 0, 0), bg_rect, border_radius=8)

        # Blit the text again on top of the background
        surface.blit(text_surf, text_rect)

        # Cache button rect for event handling
        self._button_rect = bg_rect