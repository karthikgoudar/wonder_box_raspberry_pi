import pygame
from ui.screen_base import Screen


START_TEXT = "Press to Start"


class IdleScreen(Screen):
    def __init__(self, on_start):
        self.on_start = on_start

    def handle_event(self, event):
        # handle input events
        # Accept multiple input types (Mac, touchscreen, mouse, keyboard)
        if event.type in (
            pygame.MOUSEBUTTONDOWN,  # mouse / physical click
            pygame.FINGERDOWN,       # trackpad / touchscreen
            pygame.KEYDOWN           # keyboard fallback
        ):
            self.on_start()

    def render(self, surface):
        from ui.background import draw_background
        draw_background(surface)

        from ui.font import fit_text_block
        sw, sh = surface.get_size()
        # One line, about 70% of the screen width, centred both ways
        size, lines, step = fit_text_block(START_TEXT, int(sw * 0.70), int(sh * 0.3), int(sh * 0.16), 24, max_lines=1)
        line = lines[0]
        surface.blit(line, line.get_rect(center=(sw // 2, sh // 2)))
