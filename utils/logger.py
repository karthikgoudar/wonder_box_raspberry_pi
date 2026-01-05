import json
import os
from datetime import datetime
from pathlib import Path

# Always resolve logs directory relative to the repository root, not cwd
_BASE = Path(__file__).resolve().parent.parent
LOG_DIR = _BASE / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def log_event(state, event, details=None, error=None):
    log = {
        "timestamp": datetime.utcnow().isoformat(),
        "state": state,
        "event": event,
        "details": details,
        "error": error
    }

    filename = LOG_DIR / f"log_{datetime.utcnow().date()}.jsonl"
    with open(filename, "a") as f:
        f.write(json.dumps(log) + "\n")
