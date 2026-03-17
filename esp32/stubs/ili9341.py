# stubs/ili9341.py — ILI9341 TFT driver stub for PC using pygame
# Implements the same API surface that display_service.py calls.

import pygame

# Re-export the colour helper so `from ili9341 import Display, color565` works
def color565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


class Display:
    """
    pygame-based ILI9341 stub.
    Window size matches the configured display resolution.
    """

    def __init__(self, spi, cs, dc, rst, width=320, height=240, rotation=0):
        self._w = width
        self._h = height

        if not pygame.get_init():
            pygame.init()

        self._screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Wonder Box  [PC Sim]  SPACE / Click = button")
        self._screen.fill((0, 0, 0))
        pygame.display.flip()

        # Font cache: size → pygame.Font
        self._fonts = {}
        print(f"[ili9341 STUB] pygame display {width}x{height} ready")

    # ── helpers ──────────────────────────────────────────

    def _font(self, size):
        if size not in self._fonts:
            self._fonts[size] = pygame.font.SysFont("monospace", size)
        return self._fonts[size]

    @staticmethod
    def _rgb565_to_rgb(color):
        r = ((color >> 11) & 0x1F) << 3
        g = ((color >> 5)  & 0x3F) << 2
        b = (color & 0x1F) << 3
        return (r, g, b)

    # ── public API (matches ili9341 driver) ─────────────

    def clear(self, color=0x0000):
        self._screen.fill(self._rgb565_to_rgb(color))
        pygame.display.flip()

    def draw_text8x8(self, x, y, text, color, font_size=1):
        rgb   = self._rgb565_to_rgb(color)
        font  = self._font(8 * font_size)
        surf  = font.render(str(text), True, rgb)
        self._screen.blit(surf, (x, y))
        pygame.display.flip()

    def draw_text(self, x, y, text, color):
        self.draw_text8x8(x, y, text, color, font_size=2)

    def block(self, x0, y0, x1, y1, data):
        """
        Write a rectangle of RGB565 pixels.
        data is a bytes/bytearray of (w*h*2) bytes, big-endian RGB565.
        """
        w = x1 - x0 + 1
        h = y1 - y0 + 1
        total = w * h

        try:
            import numpy as np
            # data is big-endian RGB565: high byte first, low byte second
            arr = np.frombuffer(data, dtype=np.uint8).reshape(total, 2)
            rgb565 = (arr[:, 0].astype(np.uint16) << 8) | arr[:, 1].astype(np.uint16)
            r = ((rgb565 >> 11) & 0x1F).astype(np.uint8) << 3
            g = ((rgb565 >> 5)  & 0x3F).astype(np.uint8) << 2
            b = (rgb565 & 0x1F).astype(np.uint8)          << 3
            rgb_arr = np.stack([r, g, b], axis=-1).reshape(h, w, 3)
            surf = pygame.surfarray.make_surface(rgb_arr.swapaxes(0, 1))
        except ImportError:
            # Fallback without numpy (slow but correct)
            surf = pygame.Surface((w, h))
            for i in range(total):
                hi = data[i * 2]
                lo = data[i * 2 + 1]
                rgb565 = (hi << 8) | lo
                surf.set_at(
                    (i % w, i // w),
                    self._rgb565_to_rgb(rgb565),
                )

        self._screen.blit(surf, (x0, y0))

        # Flip once the last row of the display is written to avoid per-row flicker
        if y0 >= self._h - 1:
            pygame.display.flip()
