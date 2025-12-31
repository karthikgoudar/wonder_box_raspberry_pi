import pygame

from utils.timer import Timer
from core.state_machine import StateMachine
from core.states import State
from ui.screen_factory import get_screen

# ------------------------
# Pygame initialization
# ------------------------
pygame.init()
screen = pygame.display.set_mode((800, 480))
pygame.display.set_caption("Wonder Box")

# ------------------------
# Explicit event handling (IMPORTANT for macOS)
# ------------------------
pygame.event.set_allowed(None)
pygame.event.set_allowed([
    pygame.QUIT,
    pygame.MOUSEBUTTONDOWN,
    pygame.MOUSEBUTTONUP,
    pygame.FINGERDOWN,
    pygame.KEYDOWN
])

clock = pygame.time.Clock()

# ------------------------
# Core system
# ------------------------
sm = StateMachine()

# ------------------------
# Timers (seconds)
# ------------------------
listening_timer = Timer(2.5)
processing_timer = Timer(2.5)
printing_timer = Timer(3.0)

# ------------------------
# Callbacks (UI → intent)
# ------------------------
def start_listening():
    sm.transition(State.LISTENING, reason="User tapped screen")

def approve_print():
    sm.transition(State.PRINTING, reason="User approved print")

def reset_to_idle():
    sm.transition(State.IDLE, reason="Reset to idle")

callbacks = {
    "start_listening": start_listening,
    "approve_print": approve_print,
    "reset": reset_to_idle
}

# ------------------------
# Screen + state tracking
# ------------------------
current_state = sm.get_state()
last_state = current_state
entered_state = current_state

current_screen = get_screen(current_state, callbacks)

# ------------------------
# Main loop
# ------------------------
running = True
while running:
    dt = clock.tick(60)

    # 1. Handle system + user events (ONCE)
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        current_screen.handle_event(event)

    # 2. Automatic / timed state transitions
    if current_state == State.LISTENING:
        if listening_timer.is_finished():
            sm.transition(State.PROCESSING, reason="Listening complete")

    elif current_state == State.PROCESSING:
        if processing_timer.is_finished():
            sm.transition(State.DISPLAYING, reason="Processing complete")

    elif current_state == State.PRINTING:
        if printing_timer.is_finished():
            sm.transition(State.IDLE, reason="Print complete → reset")

    elif current_state == State.DISPLAYING:
        pass  # waits for user approval

    # 3. State → Screen synchronization
    current_state = sm.get_state()
    if current_state != last_state:
        entered_state = current_state
        current_screen = get_screen(current_state, callbacks)
        last_state = current_state

        # ---- state entry actions ----
        if entered_state == State.LISTENING:
            listening_timer.start()

        elif entered_state == State.PROCESSING:
            processing_timer.start()

        elif entered_state == State.PRINTING:
            printing_timer.start()

    # 4. Update & render
    current_screen.update(dt)
    current_screen.render(screen)
    pygame.display.flip()

pygame.quit()