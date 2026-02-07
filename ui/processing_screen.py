import os
import pygame
from ui.screen_base import Screen


class ProcessingScreen(Screen):
    def __init__(self, audio_service=None, frame_image_path=None, font_path=None, font_color=None):
        self.audio_service = audio_service
        self.dots = 0
        self.last_update = 0
        # allow overriding the decorative frame image path
        self.frame_image_path_thinking = frame_image_path or os.path.join("ui", "assets", "thinking_screen_2.png")
        self._frame_image_thinking = None
        self.frame_image_path_text = frame_image_path or os.path.join("ui", "assets", "text_display_1.png")
        self._frame_image_text = None

        # font selection: prefer provided font_path, otherwise try bundled Latin font
        default_font = os.path.join("assets", "fonts", "NotoSans-Regular.ttf")
        if font_path:
            self.font_path = font_path
        elif os.path.exists(default_font):
            self.font_path = default_font
        else:
            self.font_path = None

        # color to use for text; if None we'll sample from the image when rendering
        self.font_color = font_color

    def _sample_color_from_image(self, surf: pygame.Surface):
        try:
            small = pygame.transform.smoothscale(surf, (16, 16))
            w, h = small.get_size()
            total = [0, 0, 0]
            count = 0
            for ix in range(w):
                for iy in range(h):
                    c = small.get_at((ix, iy))
                    if len(c) == 4 and c.a < 48:
                        continue
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

    def update(self, dt):
        self.last_update += dt
        if self.last_update > 500:  # ms
            self.dots = (self.dots + 1) % 4
            self.last_update = 0

    def _load_frame(self):
        if self._frame_image_thinking is not None:
            return
        try:
            self._frame_image_thinking = pygame.image.load(self.frame_image_path_thinking).convert_alpha()
        except Exception:
            self._frame_image_thinking = None
            
        if self._frame_image_text is not None:
            return
        try:
            self._frame_image_text = pygame.image.load(self.frame_image_path_text).convert_alpha()
        except Exception:
            self._frame_image_text = None

    def render(self, surface):
        surface.fill((255, 255, 255))
        from ui.font import render_text, calculate_font_size
        # Load frame (used both during processing and for the final render)
        self._load_frame()

        # If audio transcription is complete, render the final text inside the decorative frame
        if self.audio_service and self.audio_service.is_done():
            text = self.audio_service.get_text()
            if text:
                if self._frame_image_text:
                    sw, sh = surface.get_size()
                    iw, ih = self._frame_image_text.get_size()
                    max_w = int(sw * 0.9)
                    max_h = int(sh * 0.9)
                    scale = min(max_w / iw, max_h / ih)
                    new_w = max(1, int(iw * scale))
                    new_h = max(1, int(ih * scale))
                    img = pygame.transform.smoothscale(self._frame_image_text, (new_w, new_h))
                    x = (sw - new_w) // 2
                    y = (sh - new_h) // 2
                    surface.blit(img, (x, y))
                    # sample color from the text frame if not provided
                    if self.font_color is None:
                        sampled = self._sample_color_from_image(self._frame_image_text)
                        self.font_color = tuple(max(0, c - 20) for c in sampled)

                    font_size = calculate_font_size(text, new_w, new_h, min_size=12, max_size=72, padding=40)
                    center_point = (x + new_w // 2, y + new_h // 2)
                    if self.font_path:
                        try:
                            font = pygame.font.Font(self.font_path, font_size)
                            txt_surf = font.render(text, True, self.font_color)
                            shadow = font.render(text, True, (0, 0, 0))
                            tw, th = txt_surf.get_size()
                            txt_x = center_point[0] - tw // 2
                            txt_y = center_point[1] - th // 2
                            surface.blit(shadow, (txt_x + 2, txt_y + 2))
                            surface.blit(txt_surf, (txt_x, txt_y))
                        except Exception:
                            render_text(surface, text, font_size, self.font_color, center=center_point)
                    else:
                        render_text(surface, text, font_size, self.font_color, center=center_point)
                else:
                    font_size = calculate_font_size(text, surface.get_width(), surface.get_height())
                    # sample from thinking frame if available for a matching color
                    if self.font_color is None and self._frame_image_thinking:
                        sampled = self._sample_color_from_image(self._frame_image_thinking)
                        self.font_color = tuple(max(0, c - 20) for c in sampled)
                    render_text(surface, text, font_size, self.font_color or (0, 0, 0), center=True)
            else:
                # No text produced — show thinking in the frame as fallback
                thinking = "Thinking" + "." * self.dots
                if self._frame_image_thinking:
                    sw, sh = surface.get_size()
                    iw, ih = self._frame_image_thinking.get_size()
                    max_w = int(sw * 0.9)
                    max_h = int(sh * 0.9)
                    scale = min(max_w / iw, max_h / ih)
                    new_w = max(1, int(iw * scale))
                    new_h = max(1, int(ih * scale))
                    img = pygame.transform.smoothscale(self._frame_image_thinking, (new_w, new_h))
                    x = (sw - new_w) // 2
                    y = (sh - new_h) // 2
                    surface.blit(img, (x, y))
                    # sample color from thinking frame if not provided
                    if self.font_color is None:
                        sampled = self._sample_color_from_image(self._frame_image_thinking)
                        self.font_color = tuple(max(0, c - 20) for c in sampled)

                    font_size = calculate_font_size(thinking, new_w, new_h, min_size=16, max_size=48, padding=40)
                    center_point = (x + new_w // 2, y + new_h // 2)
                    if self.font_path:
                        try:
                            font = pygame.font.Font(self.font_path, font_size)
                            txt_surf = font.render(thinking, True, self.font_color)
                            shadow = font.render(thinking, True, (0, 0, 0))
                            tw, th = txt_surf.get_size()
                            txt_x = center_point[0] - tw // 2
                            txt_y = center_point[1] - th // 2
                            surface.blit(shadow, (txt_x + 2, txt_y + 2))
                            surface.blit(txt_surf, (txt_x, txt_y))
                        except Exception:
                            render_text(surface, thinking, font_size, self.font_color, center=center_point)
                    else:
                        render_text(surface, thinking, font_size, self.font_color, center=center_point)
                else:
                    render_text(surface, thinking, 48, self.font_color or (0, 0, 0), center=True)
        else:
            # Still transcribing audio - show thinking animation inside decorative image
            thinking = "Thinking" + "." * self.dots
            if self._frame_image_thinking:
                sw, sh = surface.get_size()
                iw, ih = self._frame_image_thinking.get_size()
                max_w = int(sw * 0.9)
                max_h = int(sh * 0.9)
                scale = min(max_w / iw, max_h / ih)
                new_w = max(1, int(iw * scale))
                new_h = max(1, int(ih * scale))
                img = pygame.transform.smoothscale(self._frame_image_thinking, (new_w, new_h))
                x = (sw - new_w) // 2
                y = (sh - new_h) // 2
                surface.blit(img, (x, y))
                # sample color if needed
                if self.font_color is None:
                    sampled = self._sample_color_from_image(self._frame_image_thinking)
                    self.font_color = tuple(max(0, c - 20) for c in sampled)

                font_size = calculate_font_size(thinking, new_w, new_h, min_size=16, max_size=48, padding=40)
                center_point = (x + new_w // 2, y + new_h // 2)
                if self.font_path:
                    try:
                        font = pygame.font.Font(self.font_path, font_size)
                        txt_surf = font.render(thinking, True, self.font_color)
                        shadow = font.render(thinking, True, (0, 0, 0))
                        tw, th = txt_surf.get_size()
                        txt_x = center_point[0] - tw // 2
                        txt_y = center_point[1] - th // 2
                        surface.blit(shadow, (txt_x + 2, txt_y + 2))
                        surface.blit(txt_surf, (txt_x, txt_y))
                    except Exception:
                        render_text(surface, thinking, font_size, self.font_color, center=center_point)
                else:
                    render_text(surface, thinking, font_size, self.font_color, center=center_point)
            else:
                render_text(surface, thinking, 48, (0, 0, 0), center=True)