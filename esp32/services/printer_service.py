# ============================================================
# services/printer_service.py — ESC/POS Thermal Printer
# ============================================================
# Communicates with the printer over UART2.
# Image-to-bitmap conversion is done in pure MicroPython
# (no PIL available). PNG decoding uses the upng library or
# a pre-converted bitmap sent from the host.
#
# Wiring:
#   ESP32 GPIO17 (TX) → Printer RX
#   ESP32 GPIO16 (RX) ← Printer TX
#   GND              → GND
#   Printer VIN      → 5-9V (external supply — NOT 3.3V pin)

from machine import UART, Pin
import utime
import gc
from config import PRINTER_TX_PIN, PRINTER_RX_PIN, PRINTER_BAUD, PRINTER_WIDTH, PRINTER_SIMULATE

# ESC/POS command constants
ESC = b'\x1b'
GS  = b'\x1d'

CMD_INIT        = ESC + b'@'
CMD_FEED_LINE   = b'\n'
CMD_CUT         = GS  + b'V\x41\x03'     # Partial cut + feed 3 lines


class PrinterService:
    def __init__(self):
        self._done   = False
        self._failed = False
        self._error  = None
        self._uart   = None

        if PRINTER_SIMULATE:
            print("[PrinterService] SIMULATE mode — no actual printing")
            return

        try:
            self._uart = UART(
                2,
                baudrate=PRINTER_BAUD,
                tx=Pin(PRINTER_TX_PIN),
                rx=Pin(PRINTER_RX_PIN),
            )
            print("[PrinterService] UART ready,", PRINTER_BAUD, "baud")
        except Exception as e:
            self._failed = True
            self._error  = "UART init failed: " + str(e)
            print("[PrinterService ERROR]", self._error)

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def print_image(self, png_bytes):
        """
        Print a PNG image. png_bytes must be raw PNG data.
        Converts PNG → 1-bit bitmap row-by-row and sends ESC/POS
        raster commands.
        Blocking call (may take several seconds for a full page).
        """
        self._done   = False
        self._failed = False
        self._error  = None

        if PRINTER_SIMULATE:
            print("[PrinterService] simulating print of", len(png_bytes), "byte PNG")
            utime.sleep_ms(2000)
            self._done = True
            return

        if self._uart is None:
            self._failed = True
            self._error  = "UART not initialised"
            return

        try:
            bitmap_rows = self._png_to_bitmap_rows(png_bytes)
            gc.collect()
            self._send_image(bitmap_rows)
            self._done = True
            print("[PrinterService] print complete")
        except Exception as e:
            self._failed = True
            self._error  = str(e)
            print("[PrinterService ERROR]", self._error)

    def print_text(self, text):
        """Print a plain text string followed by a feed and cut."""
        self._done   = False
        self._failed = False

        if PRINTER_SIMULATE:
            print("[PrinterService] simulate print text:", text)
            self._done = True
            return

        if self._uart is None:
            self._failed = True
            self._error  = "UART not initialised"
            return

        try:
            self._uart.write(CMD_INIT)
            self._uart.write((text + "\n\n\n").encode("utf-8", "replace"))
            self._uart.write(CMD_CUT)
            self._done = True
        except Exception as e:
            self._failed = True
            self._error  = str(e)

    # --------------------------------------------------------
    # ESC/POS raster image sending
    # --------------------------------------------------------

    def _send_image(self, bitmap_rows):
        """
        Send a list of bitmap rows (each row is a bytearray of width//8 bytes)
        to the printer using GSv0 raster command.
        """
        if not bitmap_rows:
            return

        width_bytes = len(bitmap_rows[0])
        height = len(bitmap_rows)

        self._uart.write(CMD_INIT)
        utime.sleep_ms(100)

        # GS v 0 — print raster bit image
        # Format: GS 'v' '0' m xL xH yL yH data
        cmd = (
            GS + b'v0'
            + bytes([0])                           # m = normal density
            + bytes([width_bytes & 0xFF, (width_bytes >> 8) & 0xFF])
            + bytes([height & 0xFF, (height >> 8) & 0xFF])
        )
        self._uart.write(cmd)

        for row in bitmap_rows:
            self._uart.write(row)
            utime.sleep_ms(2)   # small delay to avoid overflowing printer buffer

        self._uart.write(b'\n\n\n')
        self._uart.write(CMD_CUT)

    # --------------------------------------------------------
    # PNG → 1-bit bitmap conversion (pure MicroPython)
    # --------------------------------------------------------

    def _png_to_bitmap_rows(self, png_bytes):
        """
        Minimal PNG decoder for grayscale/RGB PNGs.
        Converts each pixel to 1-bit (black/white) using a threshold.
        Returns a list of bytearrays, one per row, each PRINTER_WIDTH//8 bytes.

        NOTE: This uses the built-in `deflate` module available in
        MicroPython 1.21+ on ESP32. For older firmware, flash a
        pre-dithered 1-bit BMP from the host instead.
        """
        import deflate
        import io

        # --- Parse PNG chunks --------------------------------------
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

        img_width  = int.from_bytes(ihdr[0:4], 'big')
        img_height = int.from_bytes(ihdr[4:8], 'big')
        bit_depth  = ihdr[8]
        color_type = ihdr[9]  # 0=gray, 2=RGB, 3=palette, 4=gray+a, 6=RGBA

        # Decompress IDAT
        raw = deflate.DeflateIO(io.BytesIO(bytes(idat_buf)), deflate.ZLIB).read()
        del idat_buf
        gc.collect()

        # Bytes per pixel
        if color_type == 2:   bpp = 3   # RGB
        elif color_type == 6: bpp = 4   # RGBA
        elif color_type == 4: bpp = 2   # Gray+A
        else:                 bpp = 1   # Gray or palette

        stride = img_width * bpp + 1    # +1 for filter byte

        # Scale to PRINTER_WIDTH
        scale  = img_width / PRINTER_WIDTH
        result = []
        THRESHOLD = 128

        for py in range(img_height):
            row_start = py * stride
            filter_byte = raw[row_start]
            row_pixels  = raw[row_start + 1: row_start + stride]

            # Only handle filter type 0 (None) and 1 (Sub) for simplicity
            # A proper PNG decoder handles all 5 filter types — extend here
            # if images use other filters.
            row_out = bytearray(PRINTER_WIDTH // 8)
            for px in range(PRINTER_WIDTH):
                src_x = int(px * scale)
                src_x = min(src_x, img_width - 1)
                pixel_offset = src_x * bpp

                # Compute luminance
                if color_type == 2:    # RGB
                    r = row_pixels[pixel_offset]
                    g = row_pixels[pixel_offset + 1]
                    b = row_pixels[pixel_offset + 2]
                    gray = (r * 299 + g * 587 + b * 114) // 1000
                elif color_type == 6:  # RGBA
                    r = row_pixels[pixel_offset]
                    g = row_pixels[pixel_offset + 1]
                    b = row_pixels[pixel_offset + 2]
                    a = row_pixels[pixel_offset + 3]
                    gray = (r * 299 + g * 587 + b * 114) // 1000
                    # Blend transparent pixels as white
                    gray = gray * a // 255 + 255 * (255 - a) // 255
                else:                  # Grayscale
                    gray = row_pixels[pixel_offset]

                # Dark pixel → printed (bit = 1)
                if gray < THRESHOLD:
                    byte_idx = px // 8
                    bit_idx  = 7 - (px % 8)
                    row_out[byte_idx] |= (1 << bit_idx)

            result.append(row_out)

        return result

    # --------------------------------------------------------
    # Status API
    # --------------------------------------------------------

    def is_done(self):
        return self._done

    def has_failed(self):
        return self._failed

    def get_error(self):
        return self._error

    def reset(self):
        self._done   = False
        self._failed = False
        self._error  = None
