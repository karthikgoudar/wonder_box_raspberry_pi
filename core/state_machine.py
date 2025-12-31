from core.states import State
from utils.logger import log_event

class StateMachine:
    def __init__(self):
        self.state = State.IDLE
        log_event(self.state.name, "INIT")

    def transition(self, new_state, reason=None):
        print(f"STATE: {self.state.name} -> {new_state.name} ({reason})")
        log_event(
            self.state.name,
            "STATE_TRANSITION",
            details={
                "to": new_state.name,
                "reason": reason
            }
        )
        self.state = new_state

    def get_state(self):
        return self.state
