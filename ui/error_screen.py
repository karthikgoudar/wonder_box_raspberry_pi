import pygame
from ui.screen_base import Screen


class ErrorScreen(Screen):
    """Only for guidance a child can act on. Any other problem sends the
    app straight back to "Press to Start" (see main.py), with no message."""

    # Friendly words for backend error codes a child can fix by trying again
    MESSAGES = {
        "LANGUAGE_NOT_SUPPORTED": ("Please speak in English,", "Kannada or Hindi"),
        "NO_STORY": ("No stories yet.", "Ask me for a picture!"),
    }

    def __init__(self, callbacks, ai_service=None):
        self.callbacks = callbacks
        self.font = None
        self.lines = self.message_for(ai_service)

    @classmethod
    def message_for(cls, ai_service):
        """The friendly message for the last failure, or None for any other problem."""
        code = ai_service.get_error_code() if ai_service else None
        return cls.MESSAGES.get(code)

    def handle_event(self, event):
        # Any interaction resets the system
        if event.type in (
            pygame.MOUSEBUTTONDOWN,
            pygame.FINGERDOWN,
            pygame.KEYDOWN
        ):
            # Safe reset path
            if "reset" in self.callbacks:
                self.callbacks["reset"]()

    def render(self, surface):
        from ui.background import draw_background
        draw_background(surface)
        from ui.font import render_text
        cx, cy = surface.get_rect().center
        from ui.font import ui_scale
        s = ui_scale(surface)
        if self.lines:
            first, second = self.lines
            render_text(surface, first, int(40 * s), (40, 40, 160), center=(cx, cy - int(60 * s)))
            render_text(surface, second, int(40 * s), (40, 40, 160), center=(cx, cy - int(15 * s)))
            render_text(surface, "Press to try again", int(32 * s), (100, 100, 100), center=(cx, cy + int(45 * s)))