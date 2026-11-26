import pygame

from ui.screen_base import Screen


def _wrap(text, size, max_width):
    from ui.font import render_text
    probe = pygame.Surface((1, 1), flags=pygame.SRCALPHA)
    width = lambda t: render_text(probe, t, size, (0, 0, 0), center=False)[0].get_width()
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if not current or width(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class StoryScreen(Screen):
    """Scene picture on top, the words being narrated underneath."""

    PAD = 20
    IMAGE_SHARE = 0.70  # of the screen height

    def __init__(self, player=None):
        self.player = player
        self._scaled = None
        self._scaled_key = None
        self._text_cache = {}

    def _fit_text(self, text, max_width, max_height, start):
        key = (text, max_width, max_height, start)
        if key not in self._text_cache:
            for size in range(start, 19, -2):
                lines = _wrap(text, size, max_width)
                if int(size * 1.3) * len(lines) <= max_height:
                    break
            self._text_cache = {key: (size, lines)}
        return self._text_cache[key]

    def _draw_words(self, surface, text, top, bottom, start_size, color=(0, 0, 0)):
        from ui.font import render_text
        sw = surface.get_width()
        size, lines = self._fit_text(text, sw - 2 * self.PAD, bottom - top, start_size)
        line_h = int(size * 1.3)
        y = top + max(0, (bottom - top - line_h * len(lines)) // 2)
        for line in lines:
            render_text(surface, line, size, color, center=(sw // 2, y + line_h // 2))
            y += line_h

    def render(self, surface):
        from ui.font import ui_scale
        surface.fill((255, 255, 255))
        sw, sh = surface.get_size()
        s = ui_scale(surface)
        p = self.player
        story = getattr(p, "story", None)
        if story is None:
            return

        image_bottom = int(sh * self.IMAGE_SHARE)
        img = p.image
        if img is None:
            self._draw_words(surface, story.title, self.PAD, image_bottom, int(52 * s))
        else:
            key = (id(img), sw, image_bottom)
            if key != self._scaled_key:
                box_w, box_h = sw - 2 * self.PAD, image_bottom - 2 * self.PAD
                iw, ih = img.get_size()
                k = min(box_w / iw, box_h / ih)
                self._scaled = pygame.transform.smoothscale(img, (max(1, int(iw * k)), max(1, int(ih * k))))
                self._scaled_key = key
            surface.blit(self._scaled, self._scaled.get_rect(center=(sw // 2, image_bottom // 2)))

        if p.narration_done:
            waiting = p.prints_waiting()
            words = "Printing your stickers..." if waiting > 1 else "Printing your sticker..."
            self._draw_words(surface, words, image_bottom, sh - self.PAD, int(40 * s), (100, 100, 100))
        elif p.sentence:
            self._draw_words(surface, p.sentence, image_bottom, sh - self.PAD, int(40 * s))
