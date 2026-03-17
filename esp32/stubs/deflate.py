# stubs/deflate.py — MicroPython deflate → CPython zlib
import zlib
import io

ZLIB = 0
DEFLATE = 1

class DeflateIO:
    def __init__(self, stream, mode=ZLIB):
        self._data = stream.read()
        self._mode = mode

    def read(self):
        if self._mode == ZLIB:
            return zlib.decompress(self._data)
        # Raw deflate (wbits = -15)
        return zlib.decompress(self._data, -15)
