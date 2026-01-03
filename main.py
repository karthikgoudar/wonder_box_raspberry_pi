import pygame
import re

from core.state_machine import StateMachine
from core.states import State
from ui.screen_factory import get_screen
from services.audio_service import AudioService
from utils.timer import Timer

# ------------------------
# Services
# ------------------------
audio_service = AudioService()

# ------------------------
# Pygame initialization
# ------------------------
pygame.init()
screen = pygame.display.set_mode((800, 480))
pygame.display.set_caption("Wonder Box")

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
# Timers
# ------------------------
printing_timer = Timer(3.0)

# ------------------------
# Callbacks (UI → intent)
# ------------------------
def start_listening():
    sm.transition(State.LISTENING, reason="Button pressed (start listening)")

def reset_to_idle():
    # Clear audio state, displayed image, and return FSM to IDLE
    try:
        audio_service.reset()
    except Exception:
        pass
    try:
        from ui import current_image
        current_image.set_image(None)
    except Exception:
        pass
    sm.transition(State.IDLE, reason="Reset from UI/Error")

callbacks = {
    "start_listening": start_listening
}
callbacks["reset"] = reset_to_idle


# Minimal text normalization: decide whether to treat recognized text as
# Latin (English/Hinglish) or Devanagari (Hindi) based on presence of
# Latin letters. This must be applied at the UI boundary only.
def normalize_text_mode(text: str) -> str:
    if text is None:
        return text
    # If any ASCII Latin letters present, treat as latin (Hinglish/English)
    if re.search(r"[A-Za-z]", text):
        try:
            print("[TEXT MODE] latin", flush=True)
        except Exception:
            pass
        return text
    else:
        try:
            print("[TEXT MODE] devanagari", flush=True)
        except Exception:
            pass
        return text

# ------------------------
# Screen + state tracking
# ------------------------
current_state = sm.get_state()
last_state = current_state
current_screen = get_screen(current_state, callbacks)

# ------------------------
# Main loop
# ------------------------
running = True
while running:
    dt = clock.tick(60)

    # ------------------------
    # 1. Event handling
    # ------------------------
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        # Button RELEASE ends listening
        if event.type in (pygame.MOUSEBUTTONUP, pygame.FINGERUP, pygame.KEYUP):
            # check the live FSM state (sm.get_state()) not the cached `current_state`
            if sm.get_state() == State.LISTENING:
                audio_service.stop_recording()
                sm.transition(State.PROCESSING, reason="Button released (stop listening)")
                continue

        current_screen.handle_event(event)

    # ------------------------
    # 2. State logic
    # ------------------------
    if current_state == State.PROCESSING:
        audio_service.update()

        if audio_service.has_failed():
            sm.transition(State.ERROR, reason=audio_service.get_error())

        elif audio_service.is_done():
            recognized_text = audio_service.get_text()
            # Clear, unambiguous, flushed CLI log so recognition is always visible
            #print(f"[AUDIO DONE] {recognized_text}", flush=True)

            # --- generate placeholder image ---
            from ui import current_image
            img = pygame.Surface(screen.get_size())
            img.fill((200, 180, 120))
            # Use centralized Unicode renderer to support Devanagari + Latin
            from ui.font import render_text
            # Apply minimal text-mode normalization at the UI boundary
            display_text = normalize_text_mode(recognized_text)
            render_text(img, display_text, 36, (0, 0, 0), center=True)
            current_image.set_image(img)

            audio_service.reset()
            sm.transition(State.PRINTING, reason="Audio processed")

    elif current_state == State.PRINTING:
        if printing_timer.is_finished():
            sm.transition(State.IDLE, reason="Print complete → reset")

    # ------------------------
    # 3. State entry actions
    # ------------------------
    current_state = sm.get_state()
    if current_state != last_state:
        current_screen = get_screen(current_state, callbacks)
        last_state = current_state

        if current_state == State.LISTENING:
            audio_service.start_recording()

        elif current_state == State.PRINTING:
            printing_timer.start()

        elif current_state == State.IDLE:
            from ui import current_image
            current_image.set_image(None)

    # ------------------------
    # 4. Render
    # ------------------------
    current_screen.update(dt)
    current_screen.render(screen)
    pygame.display.flip()

pygame.quit()