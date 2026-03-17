# ============================================================
# core/state_machine.py — Lightweight FSM for ESP32
# ============================================================
from core.states import IDLE, STATE_NAMES
from utils.logger import log_event

class StateMachine:
    def __init__(self):
        self.state = IDLE
        log_event(STATE_NAMES[self.state], "INIT")

    def transition(self, new_state, reason=None):
        old_name = STATE_NAMES.get(self.state, str(self.state))
        new_name = STATE_NAMES.get(new_state, str(new_state))
        print("[STATE]", old_name, "->", new_name, "(", reason, ")")
        log_event(old_name, "STATE_TRANSITION", detail=new_name)
        self.state = new_state

    def get_state(self):
        return self.state
