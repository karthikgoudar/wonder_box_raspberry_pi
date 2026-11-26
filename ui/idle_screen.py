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
        surface.fill((255, 255, 255))

        from ui.font import fit_text_block
        sw, sh = surface.get_size()
        # As big as fits: one or two lines across most of the screen
        size, lines, step = fit_text_block(START_TEXT, int(sw * 0.88), int(sh * 0.62), int(sh * 0.22), 24)
        top = (sh - step * len(lines)) // 2
        for i, line in enumerate(lines):
            surface.blit(line, line.get_rect(midtop=(sw // 2, top + i * step)))