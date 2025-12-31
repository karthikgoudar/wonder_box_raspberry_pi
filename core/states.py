from enum import Enum, auto

class State(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    DISPLAYING = auto()
    PRINTING = auto()
    ERROR = auto()
