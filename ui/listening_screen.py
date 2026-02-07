import os
import pygame
from ui.screen_base import Screen


class ListeningScreen(Screen):
    def __init__(self, image_path=None):
        # Default image path under ui/assets/listening_screen.png
        self.image_path = image_path or os.path.join("ui", "assets", "listening_screen_1.png")
        self._image = None
        self.dots = 0
        self.last_update = 0

    def handle_event(self, event):
        # Don't consume events - let main.py handle them
        pass
    
    def update(self, dt):
        self.last_update += dt
        if self.last_update > 500:  # ms
            self.dots = (self.dots + 1) % 4
            self.last_update = 0
    
    def _load_image(self):
        if self._image is not None:
            return
        try:
            self._image = pygame.image.load(self.image_path).convert_alpha()
        except Exception:
            self._image = None

    def render(self, surface):
        surface.fill((255, 255, 255))

        self._load_image()

        from ui.font import render_text, calculate_font_size

        if self._image:
            sw, sh = surface.get_size()
            iw, ih = self._image.get_size()

            # scale image to fit within 90% of the window
            max_w = int(sw * 0.9)
            max_h = int(sh * 0.9)
            scale = min(max_w / iw, max_h / ih)
            new_w = max(1, int(iw * scale))
            new_h = max(1, int(ih * scale))

            img = pygame.transform.smoothscale(self._image, (new_w, new_h))

            x = (sw - new_w) // 2
            y = (sh - new_h) // 2
            surface.blit(img, (x, y))

            # center the text in the image box
            text = "Listening..."
            # pick a font size that fits inside the inner area of the image
            font_size = calculate_font_size(text, new_w, new_h, min_size=18, max_size=64, padding=40)
            center_point = (x + new_w // 2, y + new_h // 2)
            render_text(surface, "Listening" + "." * self.dots, font_size, (0, 0, 0), center=center_point)
        else:
            # fallback: center text on full surface
            render_text(surface, "Listening" + "." * self.dots, 48, (0, 0, 0), center=center_point)

    