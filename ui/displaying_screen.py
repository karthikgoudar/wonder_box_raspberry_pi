import pygame
from ui.screen_base import Screen
from ui.current_image import get_image


class DisplayingScreen(Screen):
    def __init__(self):
        # Displaying only draws the current image (no texts)
        pass

    def handle_event(self, event):
        # DISPLAYING is informational only in the new flow; ignore input
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