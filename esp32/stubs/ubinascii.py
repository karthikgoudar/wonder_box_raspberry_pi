# stubs/ubinascii.py — MicroPython ubinascii → CPython base64/binascii
import base64 as _b64
import binascii as _ba

def a2b_base64(s):
    # MicroPython passes the raw b64 string; Python's b64decode handles it
    if isinstance(s, str):
        s = s.encode()
    return _b64.b64decode(s)

def b2a_base64(b):
    return _b64.b64encode(b)

hexlify = _ba.hexlify
unhexlify = _ba.unhexlify
