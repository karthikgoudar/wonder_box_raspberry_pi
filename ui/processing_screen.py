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

    def _measure_line_width(self, text, size):
        from ui.font import render_text
        temp = pygame.Surface((1, 1), flags=pygame.SRCALPHA)
        surf, _ = render_text(temp, text, size, (0, 0, 0), center=False)
        return surf.get_width()

    def _wrap_text(self, text, size, max_width):
        words = text.split()
        if not words:
            return []

        lines = []
        current = words[0]

        for word in words[1:]:
            candidate = f"{current} {word}"
            if self._measure_line_width(candidate, size) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word

        lines.append(current)
        return lines

    def _fit_wrapped_text(self, text, max_width, max_height):
        for size in range(56, 19, -2):
            lines = self._wrap_text(text, size, max_width)
            line_height = int(size * 1.35)
            total_height = line_height * max(1, len(lines))
            if total_height <= max_height:
                return size, lines, line_height

        min_size = 20
        lines = self._wrap_text(text, min_size, max_width)
        return min_size, lines, int(min_size * 1.35)

    def render(self, surface):
        surface.fill((255, 255, 255))
        from ui.font import render_text
        
        # Check if audio transcription is complete
        if self.audio_service and self.audio_service.is_done():
            # Show the transcribed text with auto-sized font
            text = self.audio_service.get_text()
            if text:
                sw, sh = surface.get_size()
                horizontal_padding = 28
                vertical_padding = 24
                max_width = sw - (horizontal_padding * 2)
                max_height = sh - (vertical_padding * 2)

                font_size, lines, line_height = self._fit_wrapped_text(text, max_width, max_height)

                # Keep short text centered; start longer text from top for readability
                if len(lines) <= 1:
                    render_text(surface, lines[0], font_size, (0, 0, 0), center=True)
                else:
                    y = vertical_padding
                    for line in lines:
                        render_text(surface, line, font_size, (0, 0, 0), center=(sw // 2, y + line_height // 2))
                        y += line_height
            else:
                # Fallback if text is empty
                render_text(surface, "Thinking" + "." * self.dots, 48, (0, 0, 0), center=True)
        else:
            # Still transcribing audio - show thinking animation
            render_text(surface, "Thinking" + "." * self.dots, 48, (0, 0, 0), center=True)