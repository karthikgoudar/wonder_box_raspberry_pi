# ============================================================
# services/display_service.py — SPI TFT Display (ILI9341)
# ============================================================
# Drives a 320x240 ILI9341 TFT (common, cheap, widely supported).
# Uses the `ili9341` MicroPython driver.
# Install via: mip.install("github:rdagger/micropython-ili9341")
#
# Wiring (default pins in config.py):
#   SCK  → SPI clock
#   MOSI → SPI data
#   MISO → SPI read (not always needed for display-only)
#   CS   → Chip select
#   DC   → Data/Command
#   RST  → Reset
#
# This service provides simple screen helpers used by the FSM:
#   show_idle()       — idle animation / prompt
#   show_listening()  — recording indicator
#   show_processing() — thinking animation
#   show_image()      — display the generated PNG
#   show_error()      — error message
#   show_printing()   — printing indicator

from machine import SPI, Pin
import utime
import gc
from config import (
    DISPLAY_SCK_PIN, DISPLAY_MOSI_PIN, DISPLAY_MISO_PIN,
    DISPLAY_CS_PIN, DISPLAY_DC_PIN, DISPLAY_RST_PIN,
    DISPLAY_WIDTH, DISPLAY_HEIGHT,
)

# Colour constants (RGB565)
BLACK  = 0x0000
WHITE  = 0xFFFF
RED    = 0xF800
GREEN  = 0x07E0
BLUE   = 0x001F
YELLOW = 0xFFE0
GRAY   = 0x8410


class DisplayService:
    def __init__(self):
        self._dots = 0
        self._last_dot_ms = 0
        self._tft = None

        try:
            from ili9341 import Display, color565
            self._color565 = color565

            spi = SPI(
                1,
                baudrate=40_000_000,
                sck=Pin(DISPLAY_SCK_PIN),
                mosi=Pin(DISPLAY_MOSI_PIN),
                miso=Pin(DISPLAY_MISO_PIN),
            )
            self._tft = Display(
                spi,
                cs=Pin(DISPLAY_CS_PIN),
                dc=Pin(DISPLAY_DC_PIN),
                rst=Pin(DISPLAY_RST_PIN),
                width=DISPLAY_WIDTH,
                height=DISPLAY_HEIGHT,
                rotation=0,
            )
            print("[DisplayService] ILI9341 ready")
        except ImportError:
            print("[DisplayService] WARNING: ili9341 driver not installed.")
            print("  Install with: import mip; mip.install('github:rdagger/micropython-ili9341')")
        except Exception as e:
            print("[DisplayService ERROR]", e)

    # --------------------------------------------------------
    # Screen states
    # --------------------------------------------------------

    def show_idle(self):
        if not self._tft:
            return
        self._tft.clear(WHITE)
        self._draw_centered_text("Hold button to talk", 80,  BLACK, font_size=2)

    def show_listening(self):
        if not self._tft:
            return
        self._tft.clear(WHITE)
        self._draw_centered_text("Listening...", 100, BLACK, font_size=2)
        self._draw_centered_text("Release when done", 130, BLACK, font_size=2)

    def show_processing(self, dots=0):
        if not self._tft:
            return
        self._tft.clear(WHITE)
        label = "Thinking" + "." * dots
        self._draw_centered_text(label, 110, BLACK, font_size=2)

    def show_image(self, png_bytes):
        """
        Decode and display PNG bytes on the TFT.
        Scales the image to fit the display.
        Requires the display driver to support pixel-level drawing.
        """
        if not self._tft:
            return
        try:
            self._tft.clear(WHITE)
            self._render_png(png_bytes)
        except Exception as e:
            print("[DisplayService] image render error:", e)
            self.show_error("Image error")

    def show_printing(self):
        if not self._tft:
            return
        self._tft.clear(WHITE)
        self._draw_centered_text("Printing...", 110, BLACK, font_size=2)

    def show_error(self, message="Error"):
        if not self._tft:
            return
        self._tft.clear(WHITE)
        self._draw_centered_text("ERROR", 80, BLACK, font_size=2)
        self._draw_centered_text(str(message)[:30], 130, BLACK, font_size=1)

    def update_dots(self):
        """
        Call every loop while in PROCESSING state to animate dots.
        Returns the current dot count (0-3).
        """
        now = utime.ticks_ms()
        if utime.ticks_diff(now, self._last_dot_ms) > 500:
            self._dots = (self._dots + 1) % 4
            self._last_dot_ms = now
        return self._dots

    # --------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------

    def _draw_centered_text(self, text, y, color, font_size=2, bold=True):
        if not self._tft:
            return
        char_width = 8 * font_size
        text_width = len(text) * char_width
        x = max(0, (DISPLAY_WIDTH - text_width) // 2)
        try:
            if bold:
                # Draw twice — offset by 1px to fake bold
                self._tft.draw_text8x8(x,     y, text, color, font_size=font_size)
                self._tft.draw_text8x8(x + 1, y, text, color, font_size=font_size)
            else:
                self._tft.draw_text8x8(x, y, text, color, font_size=font_size)
        except Exception:
            pass

    def _render_png(self, png_bytes):
        """
        Minimal PNG → RGB565 pixel-by-pixel rendering.
        Uses MicroPython 1.21+ built-in deflate for IDAT decompression.
        For better performance, use a pre-converted RGB565 raw file.
        """
        import deflate
        import io

        if png_bytes[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError("not a valid PNG")

        offset = 8
        ihdr = None
        idat_buf = bytearray()

        while offset < len(png_bytes):
            length = int.from_bytes(png_bytes[offset:offset+4], 'big')
            chunk_type = png_bytes[offset+4:offset+8]
            chunk_data = png_bytes[offset+8:offset+8+length]
            offset += 12 + length

            if chunk_type == b'IHDR':
                ihdr = chunk_data
            elif chunk_type == b'IDAT':
                idat_buf.extend(chunk_data)
            elif chunk_type == b'IEND':
                break

        if ihdr is None:
            raise ValueError("PNG missing IHDR")

        img_w  = int.from_bytes(ihdr[0:4], 'big')
        img_h  = int.from_bytes(ihdr[4:8], 'big')
        color_type = ihdr[9]

        raw = deflate.DeflateIO(io.BytesIO(bytes(idat_buf)), deflate.ZLIB).read()
        del idat_buf
        gc.collect()

        if color_type == 2:   bpp = 3
        elif color_type == 6: bpp = 4
        elif color_type == 4: bpp = 2
        else:                 bpp = 1

        stride   = img_w * bpp + 1
        scale_x  = img_w / DISPLAY_WIDTH
        scale_y  = img_h / DISPLAY_HEIGHT

        for dy in range(DISPLAY_HEIGHT):
            sy         = int(dy * scale_y)
            row_start  = sy * stride + 1  # skip filter byte
            row_pixels = raw[row_start: row_start + img_w * bpp]

            row_buf = bytearray(DISPLAY_WIDTH * 2)  # RGB565, 2 bytes per pixel
            for dx in range(DISPLAY_WIDTH):
                sx = int(dx * scale_x)
                sx = min(sx, img_w - 1)
                off = sx * bpp

                if color_type == 2:
                    r, g, b = row_pixels[off], row_pixels[off+1], row_pixels[off+2]
                elif color_type == 6:
                    r, g, b = row_pixels[off], row_pixels[off+1], row_pixels[off+2]
                else:
                    gray = row_pixels[off]
                    r = g = b = gray

                # Pack to RGB565
                rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                row_buf[dx*2]   = (rgb565 >> 8) & 0xFF
                row_buf[dx*2+1] = rgb565 & 0xFF

            # Write the whole row at once for speed
            self._tft.block(0, dy, DISPLAY_WIDTH - 1, dy, bytes(row_buf))
        gc.collect()
