# stubs/utime.py — MicroPython utime → CPython time
import time as _time

def sleep_ms(ms):
    # Also pump pygame events so the window stays responsive
    try:
        import pygame
        pygame.event.pump()
    except Exception:
        pass
    _time.sleep(ms / 1000.0)

def sleep(s):
    _time.sleep(s)

def ticks_ms():
    return int(_time.monotonic() * 1000)

def ticks_diff(new, old):
    return new - old

def localtime():
    t = _time.localtime()
    return (t.tm_year, t.tm_mon, t.tm_mday,
            t.tm_hour, t.tm_min, t.tm_sec,
            t.tm_wday, t.tm_yday)
