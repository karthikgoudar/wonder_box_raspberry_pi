import pygame
from ui.screen_base import Screen

class ProcessingScreen(Screen):
    def __init__(self, audio_service=None, text_source=None):
        self.audio_service = audio_service
        # What the child said comes back from the backend via ai_service.get_text();
        # AudioService only records, it has no text.
        self.text_source = text_source
        self.dots = 0
        self.last_update = 0

    def update(self, dt):
        self.last_update += dt
        if self.last_update > 500:  # ms
            self.dots = (self.dots + 1) % 4
            self.last_update = 0

    def render(self, surface):
        surface.fill((255, 255, 255))
        from ui.font import render_text, ui_scale
        
        # What the child said, once the backend has transcribed it
        get_text = getattr(self.text_source, "get_text", None)
        text = get_text() if callable(get_text) else None
        if not text:
            # Still waiting for the backend - show thinking animation
            render_text(surface, "Thinking" + "." * self.dots, int(48 * ui_scale(surface)), (0, 0, 0), center=True)
            return

        # Left-aligned from the top left, as big as the words allow
        from ui.font import fit_text_block
        sw, sh = surface.get_size()
        pad = max(20, sw // 24)
        size, lines, step = fit_text_block(text, sw - 2 * pad, sh - 2 * pad, int(sh * 0.18), 20)
        for i, line in enumerate(lines):
            surface.blit(line, (pad, pad + i * step))
