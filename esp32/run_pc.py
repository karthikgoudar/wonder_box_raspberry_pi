# ============================================================
# run_pc.py — Run Wonder Box ESP32 code on your PC
# ============================================================
# Injects MicroPython compatibility stubs so the esp32/ code
# runs natively on CPython with:
#   • PC microphone  → replaces I2S mic
#   • pygame window  → replaces ILI9341 TFT display
#   • SPACE / click  → replaces physical button
#   • requests lib   → replaces urequests
#   • Simulated printer (bytes saved to sim_printer_output.bin)
#
# Usage:
#   cd d:\WonderBox\Wonder-Box\esp32
#   python run_pc.py
#
# Requirements (install once):
#   pip install -r requirements_pc.txt

import sys
import os

# ── 1. Set up module search path ────────────────────────────
_here  = os.path.dirname(os.path.abspath(__file__))   # esp32/
_stubs = os.path.join(_here, "stubs")

# stubs/ must come FIRST so MicroPython modules (machine, utime …)
# resolve to our PC stubs instead of any installed packages.
sys.path.insert(0, _stubs)
sys.path.insert(1, _here)

# ── 2. Verify config.py credentials ─────────────────────────
try:
    import config
    if config.OPENAI_API_KEY.startswith("sk-YOUR"):
        print("=" * 60)
        print("  ERROR: Please set your OPENAI_API_KEY in esp32/config.py")
        print("=" * 60)
        sys.exit(1)
    if config.WIFI_SSID == "YOUR_SSID":
        print("[run_pc] Note: WIFI_SSID not set — that's fine on PC (network stub used)")
except Exception as e:
    print("Could not load config.py:", e)
    sys.exit(1)

# ── 3. Init pygame early (before any service imports it) ────
import pygame
pygame.init()
print("[run_pc] pygame initialised")
print("[run_pc] Controls:")
print("         SPACE or Left Mouse Click = hold button to record")
print("         Release                   = stop recording / trigger print")
print("         ESC                       = quit")

# ── 4. Patch PRINTER_SIMULATE so printer never writes garbage ─
#       (can override here for testing)
config.PRINTER_SIMULATE = True

# ── 5. Intercept pygame.QUIT / ESC in the utime stub ────────
#       so the window close button exits cleanly.
_orig_sleep_ms = None
def _patched_sleep_ms(ms):
    import time
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            print("[run_pc] window closed — exiting")
            pygame.quit()
            sys.exit(0)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            print("[run_pc] ESC pressed — exiting")
            pygame.quit()
            sys.exit(0)
    time.sleep(ms / 1000.0)

import utime as _utime
_utime.sleep_ms = _patched_sleep_ms

# ── 6. Run main.py ──────────────────────────────────────────
main_path = os.path.join(_here, "main.py")
print(f"[run_pc] starting main.py from {main_path}")
print("=" * 60)

with open(main_path, "r", encoding="utf-8") as _f:
    _src = _f.read()

exec(compile(_src, main_path, "exec"), {"__file__": main_path, "__name__": "__main__"})
