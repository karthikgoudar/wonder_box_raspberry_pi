# ============================================================
# utils/logger.py — Simple serial + flash logger for ESP32
# ============================================================
import utime

def log_event(state, event, detail=None, error=None):
    """
    Logs a structured event to the REPL serial console.
    Flash writes are avoided to protect ESP32 flash endurance.
    Extend this to write to a file on LittleFS if persistent
    logs are needed.
    """
    ts = utime.localtime()
    timestamp = "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(
        ts[0], ts[1], ts[2], ts[3], ts[4], ts[5]
    )
    parts = ["[LOG]", timestamp, state, event]
    if detail:
        parts.append(str(detail))
    if error:
        parts.append("ERR:" + str(error))
    print(" | ".join(parts))
