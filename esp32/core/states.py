# ============================================================
# core/states.py — State constants for ESP32 Wonder Box
# ============================================================
# MicroPython does not support the `enum` module, so we use
# plain integer constants instead.

IDLE       = 0
LISTENING  = 1
PROCESSING = 2
DISPLAYING = 3
PRINTING   = 4
ERROR      = 5

# Human-readable names (used for logging)
STATE_NAMES = {
    IDLE:       "IDLE",
    LISTENING:  "LISTENING",
    PROCESSING: "PROCESSING",
    DISPLAYING: "DISPLAYING",
    PRINTING:   "PRINTING",
    ERROR:      "ERROR",
}
