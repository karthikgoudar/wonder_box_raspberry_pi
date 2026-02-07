import os
import pygame
from ui.screen_base import Screen


class IdleScreen(Screen):
    def __init__(self, on_start, image_path=None):
        self.on_start = on_start
        # allow caller to pass a custom image path; default to assets/idle_screen.png
        self.image_path = image_path or os.path.join("ui", "assets", "idle_screen.png")
        self._image = None

    def handle_event(self, event):
        # handle input events
        # Accept multiple input types (Mac, touchscreen, mouse, keyboard)
        if event.type in (
            pygame.MOUSEBUTTONDOWN,  # mouse / physical click
            pygame.FINGERDOWN,       # trackpad / touchscreen
            pygame.KEYDOWN           # keyboard fallback
        ):
            self.on_start()

    def _load_image(self):
        # lazy-load the image so pygame.init() and display setup can happen first
        if self._image is not None:
            return
        try:
            self._image = pygame.image.load(self.image_path).convert_alpha()
        except Exception:
            self._image = None

    def render(self, surface):
        surface.fill((255, 255, 255))

        self._load_image()

        if self._image:
            # scale image to fit within the window while preserving aspect ratio
            sw, sh = surface.get_size()
            iw, ih = self._image.get_size()

            # compute max size that fits within 90% of window dimensions
            max_w = int(sw * 0.9)
            max_h = int(sh * 0.9)

            scale = min(max_w / iw, max_h / ih)
            new_w = max(1, int(iw * scale))
            new_h = max(1, int(ih * scale))

            img = pygame.transform.smoothscale(self._image, (new_w, new_h))

            # center the image
            x = (sw - new_w) // 2
            y = (sh - new_h) // 2
            surface.blit(img, (x, y))
        else:
            # fallback to text if image not available
            from ui.font import render_text
            render_text(surface, "Tap to Start", 48, (0, 0, 0), center=True)