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
    pygame.FINGERUP,
    pygame.KEYDOWN,
    pygame.KEYUP
])

clock = pygame.time.Clock()

# ------------------------
# Core system
# ------------------------
sm = StateMachine()

# ------------------------
# Timers (seconds)
# ------------------------
processing_timer = Timer(2.5)
printing_timer = Timer(3.0)

# ------------------------
# Callbacks (UI → intent)
# ------------------------
def start_listening():
    sm.transition(State.LISTENING, reason="Button pressed (start listening)")

def reset_to_idle():
    sm.transition(State.IDLE, reason="Reset to idle")

callbacks = {
    "start_listening": start_listening,
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

        # LISTENING ends on button release -> move to PROCESSING
        if event.type in (pygame.MOUSEBUTTONUP, pygame.FINGERUP, pygame.KEYUP):
            if current_state == State.LISTENING:
                sm.transition(State.PROCESSING, reason="Button released (stop listening)")
                # don't forward release to screens
                continue

        current_screen.handle_event(event)

    # 2. Automatic / timed state transitions
    if current_state == State.PROCESSING:
        if processing_timer.is_finished():
            # generate or capture the image to display during printing
            from ui import current_image
            img = pygame.Surface(screen.get_size())
            img.fill((200, 180, 120))
            font = pygame.font.SysFont(None, 36)
            text = font.render("Generated Image", True, (0, 0, 0))
            rect = text.get_rect(center=img.get_rect().center)
            img.blit(text, rect)
            current_image.set_image(img)
            sm.transition(State.PRINTING, reason="Processing complete")

    elif current_state == State.PRINTING:
        if printing_timer.is_finished():
            sm.transition(State.IDLE, reason="Print complete → reset")

    # DISPLAYING is informational only (we now auto-advance from PROCESSING to PRINTING)

    # 3. State → Screen synchronization
    current_state = sm.get_state()
    if current_state != last_state:
        entered_state = current_state
        current_screen = get_screen(current_state, callbacks)
        last_state = current_state

        # ---- state entry actions ----
        if entered_state == State.PROCESSING:
            processing_timer.start()

        elif entered_state == State.PRINTING:
            printing_timer.start()
        elif entered_state == State.IDLE:
            # clear any displayed image when returning to idle
            from ui import current_image
            current_image.set_image(None)

    # 4. Update & render
    current_screen.update(dt)
    current_screen.render(screen)
    pygame.display.flip()

pygame.quit()