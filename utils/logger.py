import json
import os
from datetime import datetime

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def log_event(state, event, details=None, error=None):
    log = {
        "timestamp": datetime.utcnow().isoformat(),
        "state": state,
        "event": event,
        "details": details,
        "error": error
    }

    filename = f"{LOG_DIR}/log_{datetime.utcnow().date()}.jsonl"
    with open(filename, "a") as f:
        f.write(json.dumps(log) + "\n")
