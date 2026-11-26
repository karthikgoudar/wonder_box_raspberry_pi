import pygame
from ui.screen_base import Screen


class ErrorScreen(Screen):
    # Friendly words for backend error codes a child can fix by trying again
    MESSAGES = {
        "LANGUAGE_NOT_SUPPORTED": ("Please speak in English,", "Kannada or Hindi"),
        "NO_STORY": ("No stories yet.", "Ask me for a picture!"),
    }

    def __init__(self, callbacks, ai_service=None):
        self.callbacks = callbacks
        self.font = None
        code = ai_service.get_error_code() if ai_service else None
        self.lines = self.MESSAGES.get(code)

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
        surface.fill((255, 255, 255))
        from ui.font import render_text
        cx, cy = surface.get_rect().center
        from ui.font import ui_scale
        s = ui_scale(surface)
        if self.lines:
            first, second = self.lines
            render_text(surface, first, int(40 * s), (40, 40, 160), center=(cx, cy - int(60 * s)))
            render_text(surface, second, int(40 * s), (40, 40, 160), center=(cx, cy - int(15 * s)))
            render_text(surface, "Tap to try again", int(32 * s), (100, 100, 100), center=(cx, cy + int(45 * s)))
            return
        # Centred on the screen (the old fixed y=220/270 only suited 320x480)
        render_text(surface, "Oops! Something went wrong.", int(40 * s), (200, 0, 0), center=(cx, cy - int(25 * s)))
        render_text(surface, "Tap to start again", int(32 * s), (100, 100, 100), center=(cx, cy + int(25 * s)))