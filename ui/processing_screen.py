import pygame
from ui.screen_base import Screen

class ProcessingScreen(Screen):
    def __init__(self, audio_service=None):
        self.audio_service = audio_service
        self.dots = 0
        self.last_update = 0

    def update(self, dt):
        self.last_update += dt
        if self.last_update > 500:  # ms
            self.dots = (self.dots + 1) % 4
            self.last_update = 0

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
                # Fallback if text is empty
                render_text(surface, "Thinking" + "." * self.dots, 48, (0, 0, 0), center=True)
        else:
            # Still transcribing audio - show thinking animation
            render_text(surface, "Thinking" + "." * self.dots, 48, (0, 0, 0), center=True)