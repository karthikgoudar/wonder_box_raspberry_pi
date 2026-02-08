import os

import pygame
from dotenv import load_dotenv

# Load .env early so all services see the same environment
load_dotenv()

from utils.timer import Timer
from utils.logger import log_event
from core.state_machine import StateMachine
from core.states import State
from ui.screen_factory import get_screen
from ui.current_image import set_image
from services.audio_service import AudioService
from services.ai_service import AIService

print(f"[MAIN] build 2026-01-04a (ai+audio wiring) file={__file__}", flush=True)
log_event("MAIN", "START", details={"file": __file__, "cwd": os.getcwd()})

# ------------------------
# Pygame initialization
# ------------------------
pygame.init()
screen = pygame.display.set_mode((600, 600))
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
audio_service = AudioService()
ai_service = AIService()
ai_started = False
last_process_status = None
print("[MAIN] services ready", flush=True)
log_event("MAIN", "SERVICES_READY")

# ------------------------
# Timers (seconds)
# ------------------------
listening_timer = Timer(10.0)
processing_timer = Timer(120)
printing_timer = Timer(10.0)
displaying_timer = Timer(120.0)

# ------------------------
# Callbacks (UI → intent)
# ------------------------
def start_listening():
    global ai_started
    set_image(None)
    ai_service.reset()
    audio_service.start_recording()
    ai_started = False
    listening_timer.start()  # Reset timer when entering LISTENING
    sm.transition(State.LISTENING, reason="Button pressed (start listening)")

def stop_listening(reason="Button released (stop listening)"):
    audio_service.stop_recording()
    sm.transition(State.PROCESSING, reason=reason)

def approve_print():
    sm.transition(State.PRINTING, reason="User approved print")

def reset_to_idle():
    sm.transition(State.IDLE, reason="Reset to idle")

def cancel():
    """Global RED button intent — transition to IDLE from allowed states.

    Mapped to ESC key (red button). Handled centrally in the main loop.
    """
    global ai_started
    # Stop audio recording if active
    if audio_service._recording:
        audio_service.stop_recording()
    # Reset services (will abandon in-flight AI thread)
    audio_service.reset()
    ai_service.reset()
    ai_started = False
    set_image(None)
    # Reset all timers to prevent stale state
    listening_timer.reset()
    processing_timer.reset()
    printing_timer.reset()
    displaying_timer.reset()
    sm.transition(State.IDLE, reason="Red button (cancel) pressed")

callbacks = {
    "start_listening": start_listening,
    "approve_print": approve_print,
    "reset": reset_to_idle
}
# expose cancel intent via callbacks for screens to call (not required)
callbacks["cancel"] = cancel

# ------------------------
# Services dict for passing to screens
# ------------------------
services = {
    "audio_service": audio_service,
    "ai_service": ai_service
}

# ------------------------
# Screen + state tracking
# ------------------------
current_state = sm.get_state()
last_state = current_state
entered_state = current_state

current_screen = get_screen(current_state, callbacks, services)

# ------------------------
# Main loop
# ------------------------
running = True
while running:
    dt = clock.tick(60)
    current_state = sm.get_state()

    # 1. Handle system + user events (ONCE)
    for event in pygame.event.get():
        current_state = sm.get_state()
        print("Event received:", event.type, "in state", current_state.name, flush=True)
        if event.type == pygame.QUIT:
            running = False
        # Global RED button handling (ESC) — cancel to IDLE from selected states
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if current_state in (State.LISTENING, State.PROCESSING, State.DISPLAYING):
                callbacks["cancel"]()
                # skip forwarding to screen
                continue

        # When listening, releasing input stops recording
        if current_state == State.LISTENING and event.type in (pygame.MOUSEBUTTONUP, pygame.FINGERUP, pygame.KEYUP):
            print("[MAIN] input released during LISTENING; stopping", flush=True)
            stop_listening()
            continue

        current_screen.handle_event(event)

    # Sync state after any event-driven transitions
    current_state = sm.get_state()

    # 2. Automatic / timed state transitions
    if current_state == State.LISTENING:
        # Fallback auto-stop if user never releases
        if listening_timer.is_finished():
            print("[MAIN] listening timer expired; stopping", flush=True)
            stop_listening(reason="Listening timeout")

    elif current_state == State.PROCESSING:
        # Finalize audio capture
        audio_service.update()
        if audio_service.has_failed():
            sm.transition(State.ERROR, reason=f"Audio failed: {audio_service.get_error()}")
        elif audio_service.is_done() and not ai_started:
            text = audio_service.get_text()
            print(f"[AUDIO DONE] {text}", flush=True)
            log_event("PROCESSING", "AUDIO_DONE", details={"text": text})
            ai_service.start_generation(text)
            log_event("PROCESSING", "AI_START", details={"prompt": text})
            ai_started = True
        else:
            if not audio_service.is_done():
                print("[AUDIO] still processing", flush=True)
            elif ai_started:
                print("[AI] already started; waiting", flush=True)

        # Poll AI generation completion
        if ai_service.has_failed():
            err = ai_service.get_error()
            log_event("PROCESSING", "AI_FAILED", error=err)
            sm.transition(State.ERROR, reason=f"AI failed: {err}")
        elif ai_started and ai_service.is_done():
            img = ai_service.get_image()
            if img is not None:
                set_image(img)
                log_event("PROCESSING", "AI_IMAGE_READY")
                sm.transition(State.DISPLAYING, reason="AI image generated")
            ai_started = False
        elif ai_started:
            pass

        # Diagnostic snapshot to ensure this branch is executing
        status = (
            audio_service.is_done(),
            audio_service.has_failed(),
            ai_started,
            ai_service.is_done(),
            ai_service.has_failed(),
        )
        if status != last_process_status:
            print(
                f"[PROCESS] audio_done={status[0]} audio_failed={status[1]} "
                f"ai_started={status[2]} ai_done={status[3]} ai_failed={status[4]}",
                flush=True,
            )
            log_event(
                "PROCESSING",
                "STATUS",
                details={
                    "audio_done": status[0],
                    "audio_failed": status[1],
                    "ai_started": status[2],
                    "ai_done": status[3],
                    "ai_failed": status[4],
                },
            )
            last_process_status = status

    elif current_state == State.PRINTING:
        if printing_timer.is_finished():
            sm.transition(State.IDLE, reason="Print complete → reset")

    elif current_state == State.DISPLAYING:
        if displaying_timer.is_finished():
            sm.transition(State.IDLE, reason="Display timeout")

    # 3. State → Screen synchronization
    current_state = sm.get_state()
    if current_state != last_state:
        entered_state = current_state
        current_screen = get_screen(current_state, callbacks, services)
        last_state = current_state

        # ---- state entry actions ----
        if entered_state == State.LISTENING:
            listening_timer.start()

        elif entered_state == State.PROCESSING:
            processing_timer.start()

        elif entered_state == State.DISPLAYING:
            displaying_timer.start()

        elif entered_state == State.PRINTING:
            printing_timer.start()

    # 4. Update & render
    current_screen.update(dt)
    current_screen.render(screen)
    pygame.display.flip()

pygame.quit()


