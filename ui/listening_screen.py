import os
import pygame
from ui.screen_base import Screen


class ListeningScreen(Screen):
    def __init__(self, image_path=None, font_path=None, font_color=None):
        # Default image path under ui/assets/listening_screen_1.png
        self.image_path = image_path or os.path.join("ui", "assets", "listening_screen_1.png")
        self._image = None
        self.dots = 0
        self.last_update = 0
        # optional custom font to better match listening image
        # if not provided, try to find a bundled Latin font under assets/fonts
        default_font = os.path.join("assets", "fonts", "NotoSans-Regular.ttf")
        if font_path:
            self.font_path = font_path
        elif os.path.exists(default_font):
            self.font_path = default_font
        else:
            self.font_path = None

        # color will be sampled from the image if not provided
        self.font_color = font_color

    def _sample_color_from_image(self, surf: pygame.Surface):
        try:
            # downscale image to speed up sampling
            small = pygame.transform.smoothscale(surf, (16, 16))
            w, h = small.get_size()
            total = [0, 0, 0]
            count = 0
            for ix in range(w):
                for iy in range(h):
                    c = small.get_at((ix, iy))
                    # if surface has alpha, skip very transparent pixels
                    if len(c) == 4 and c.a < 48:
                        continue
                    # skip near-white/blank pixels to focus on decorative colors
                    if c.r > 240 and c.g > 240 and c.b > 240:
                        continue
                    total[0] += c.r
                    total[1] += c.g
                    total[2] += c.b
                    count += 1
            if count == 0:
                return (0, 0, 0)
            return (total[0] // count, total[1] // count, total[2] // count)
        except Exception:
            return (0, 0, 0)

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
            text = "Listening"
            display = text + "." * self.dots

            # pick a font size that fits inside the inner area of the image
            font_size = calculate_font_size(display, new_w, new_h, min_size=18, max_size=64, padding=40)
            center_point = (x + new_w // 2, y + new_h // 2)

            # if font color not provided, sample a matching color from the decorative image
            if self.font_color is None:
                sampled = self._sample_color_from_image(self._image)
                # ensure good contrast: darken sampled color a bit
                self.font_color = tuple(max(0, c - 20) for c in sampled)

            # If a custom font file was provided and exists, use it to render
            if self.font_path:
                try:
                    font = pygame.font.Font(self.font_path, font_size)
                    txt_surf = font.render(display, True, self.font_color)
                    shadow = font.render(display, True, (0, 0, 0))
                    tw, th = txt_surf.get_size()
                    txt_x = center_point[0] - tw // 2
                    txt_y = center_point[1] - th // 2
                    # blit shadow then text for readability
                    surface.blit(shadow, (txt_x + 2, txt_y + 2))
                    surface.blit(txt_surf, (txt_x, txt_y))
                except Exception:
                    render_text(surface, display, font_size, self.font_color, center=center_point)
            else:
                render_text(surface, display, font_size, self.font_color, center=center_point)
        else:
            # fallback: center text on full surface
            center_point = surface.get_rect().center
            render_text(surface, "Listening" + "." * self.dots, 48, (0, 0, 0), center=center_point)

    