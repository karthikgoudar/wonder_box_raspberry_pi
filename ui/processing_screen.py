import os
import pygame
from ui.screen_base import Screen


class ProcessingScreen(Screen):
    def __init__(self, audio_service=None, frame_image_path=None):
        self.audio_service = audio_service
        self.dots = 0
        self.last_update = 0
        # allow overriding the decorative frame image path
        self.frame_image_path = frame_image_path or os.path.join("ui", "assets", "processing_frame.png")
        self._frame_image = None

    def update(self, dt):
        self.last_update += dt
        if self.last_update > 500:  # ms
            self.dots = (self.dots + 1) % 4
            self.last_update = 0

    def _load_frame(self):
        if self._frame_image is not None:
            return
        try:
            self._frame_image = pygame.image.load(self.frame_image_path).convert_alpha()
        except Exception:
            self._frame_image = None

    def render(self, surface):
        surface.fill((255, 255, 255))
        from ui.font import render_text, calculate_font_size

        # Check if audio transcription is complete
        if self.audio_service and self.audio_service.is_done():
            # Show the transcribed text with auto-sized font
            text = self.audio_service.get_text()
            if text:
                # Calculate optimal font size for the text
                font_size = calculate_font_size(text, surface.get_width(), surface.get_height())
                render_text(surface, text, font_size, (0, 0, 0), center=True)
            else:
                # Fallback: still show thinking using the frame when text empty
                self._load_frame()
                thinking = "Thinking" + "." * self.dots
                if self._frame_image:
                    sw, sh = surface.get_size()
                    iw, ih = self._frame_image.get_size()
                    max_w = int(sw * 0.9)
                    max_h = int(sh * 0.9)
                    scale = min(max_w / iw, max_h / ih)
                    new_w = max(1, int(iw * scale))
                    new_h = max(1, int(ih * scale))
                    img = pygame.transform.smoothscale(self._frame_image, (new_w, new_h))
                    x = (sw - new_w) // 2
                    y = (sh - new_h) // 2
                    surface.blit(img, (x, y))
                    font_size = calculate_font_size(thinking, new_w, new_h, min_size=16, max_size=48, padding=40)
                    center_point = (x + new_w // 2, y + new_h // 2)
                    render_text(surface, thinking, font_size, (0, 0, 0), center=center_point)
                else:
                    render_text(surface, thinking, 48, (0, 0, 0), center=True)
        else:
            # Still transcribing audio - show thinking animation inside decorative image
            self._load_frame()
            thinking = "Thinking" + "." * self.dots
            if self._frame_image:
                sw, sh = surface.get_size()
                iw, ih = self._frame_image.get_size()
                max_w = int(sw * 0.9)
                max_h = int(sh * 0.9)
                scale = min(max_w / iw, max_h / ih)
                new_w = max(1, int(iw * scale))
                new_h = max(1, int(ih * scale))
                img = pygame.transform.smoothscale(self._frame_image, (new_w, new_h))
                x = (sw - new_w) // 2
                y = (sh - new_h) // 2
                surface.blit(img, (x, y))
                font_size = calculate_font_size(thinking, new_w, new_h, min_size=16, max_size=48, padding=40)
                center_point = (x + new_w // 2, y + new_h // 2)
                render_text(surface, thinking, font_size, (0, 0, 0), center=center_point)
            else:
                render_text(surface, thinking, 48, (0, 0, 0), center=True)