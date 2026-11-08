import os
import time
import pygame
from dotenv import load_dotenv

import sys
import os

sys.stdout.reconfigure(encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"

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
from services.printer_service import PrinterService

print(f"[MAIN] build 2026-01-04a (ai+audio wiring) file={__file__}", flush=True)
log_event("MAIN", "START", details={"file": __file__, "cwd": os.getcwd()})
DEBUG_EVENTS = os.getenv("DEBUG_EVENTS", "0").lower() in ("1", "true", "yes")

# ------------------------
# Pygame initialization
# ------------------------
pygame.init()
# Logical (app) size
LOGICAL_W = int(os.getenv("SCREEN_W", "600"))
LOGICAL_H = int(os.getenv("SCREEN_H", "600"))
# Rotate degrees (clockwise). Use env var SCREEN_ROTATE_DEG, e.g. 90 or 270.
ROTATE_DEGREES = int(os.getenv("SCREEN_ROTATE_DEG", "-90"))

# FULLSCREEN=1 covers the whole display (no title bar) at its native size.
FULLSCREEN = os.getenv("FULLSCREEN", "0").lower() in ("1", "true", "yes")
# ESC closes the app. Set ESC_QUITS=0 to get the old behaviour (ESC cancels
# the current job and returns to idle).
ESC_QUITS = os.getenv("ESC_QUITS", "1").lower() in ("1", "true", "yes")

if FULLSCREEN:
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
# If rotating by 90/270 swap the physical display dimensions.
elif ROTATE_DEGREES in (90, 270, -270, -90):
    screen = pygame.display.set_mode((LOGICAL_H, LOGICAL_W))
else:
    screen = pygame.display.set_mode((LOGICAL_W, LOGICAL_H))

# Offscreen buffer where UI is rendered at logical size
buffer = pygame.Surface((LOGICAL_W, LOGICAL_H))
pygame.display.set_caption("Wonder Box")

# Instantiate ButtonService after pygame init so non-RPi input can be
# handled consistently by main (and so pygame is available if needed).
from services.button_service import ButtonService
button = ButtonService()
button_prev_held = False

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
printer_service = PrinterService()
ai_started = False
last_process_status = None
last_event_log = None
audio_wait_logged = False
ai_wait_logged = False
print("[MAIN] services ready", flush=True)
log_event("MAIN", "SERVICES_READY")

# ------------------------
# Timers (seconds)
# ------------------------
listening_timer = Timer(10.0)
processing_timer = Timer(120)
printing_timer = Timer(10.0)
displaying_timer = Timer(16.5)

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
    "ai_service": ai_service,
    "printer_service": printer_service,
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
        should_log_event = DEBUG_EVENTS or event.type in (
            pygame.QUIT,
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
            pygame.FINGERDOWN,
            pygame.FINGERUP,
            pygame.KEYDOWN,
            pygame.KEYUP,
        )
        if should_log_event:
            event_key = (event.type, current_state)
            if event_key != last_event_log:
                print("Event received:", event.type, "in state", current_state.name, flush=True)
                last_event_log = event_key
        if event.type == pygame.QUIT:
            running = False
        # ESC closes the app
        if ESC_QUITS and event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            print("[MAIN] ESC pressed; closing app", flush=True)
            running = False
            continue
        # Global RED button handling (ESC) — cancel to IDLE from selected states
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if current_state in (State.LISTENING, State.PROCESSING, State.DISPLAYING):
                callbacks["cancel"]()
                # skip forwarding to screen
                continue

        # Global input-to-start: Pressing mouse/keyboard starts LISTENING from IDLE
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN, pygame.KEYDOWN):
            if current_state == State.IDLE:
                start_listening()

        # When listening, releasing input stops recording
        if current_state == State.LISTENING and event.type in (pygame.MOUSEBUTTONUP, pygame.FINGERUP, pygame.KEYUP):
            print("[MAIN] input released during LISTENING; stopping", flush=True)
            stop_listening()
            continue

        current_screen.handle_event(event)

    # Sync state after any event-driven transitions
    current_state = sm.get_state()

    # --- Physical button polling/edge detection ---
    try:
        held = False
        if button is not None:
            held = bool(button.is_held())
    except Exception:
        held = False

    if held and not button_prev_held:
        # button pressed (edge)
        if current_state != State.LISTENING:
            start_listening()

    if not held and button_prev_held:
        # button released (edge)
        if sm.get_state() == State.LISTENING:
            stop_listening(reason="Button released (physical)")

    button_prev_held = held

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
            wav_path = audio_service.get_wav_path()
            print(f"[AUDIO DONE] {wav_path}", flush=True)
            log_event("PROCESSING", "AUDIO_DONE", details={"wav": wav_path})
            ai_service.start_generation(wav_path)
            log_event("PROCESSING", "AI_START", details={"wav": wav_path})
            ai_started = True
            audio_wait_logged = False
            ai_wait_logged = False
        else:
            if not audio_service.is_done():
                if not audio_wait_logged:
                    print("[AUDIO] still processing", flush=True)
                    audio_wait_logged = True
            elif ai_started:
                audio_wait_logged = False
                if not ai_wait_logged:
                    print("[AI] already started; waiting", flush=True)
                    ai_wait_logged = True

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
            ai_wait_logged = False
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
        # Keep image on screen for the full timer duration, regardless of
        # whether printing finishes early.
        if displaying_timer.is_finished():
            try:
                if printer_service and printer_service.has_failed():
                    sm.transition(State.ERROR, reason=f"Printer failed: {printer_service.get_error()}")
                else:
                    sm.transition(State.IDLE, reason="16.5s display complete")
            except Exception:
                sm.transition(State.IDLE, reason="16.5s display complete")

    # 3. State → Screen synchronization
    current_state = sm.get_state()
    if current_state != last_state:
        entered_state = current_state
        current_screen = get_screen(current_state, callbacks, services)
        last_state = current_state
        if entered_state != State.PROCESSING:
            audio_wait_logged = False
            ai_wait_logged = False

        # ---- state entry actions ----
        if entered_state == State.LISTENING:
            listening_timer.start()

        elif entered_state == State.PROCESSING:
            processing_timer.start()

        elif entered_state == State.DISPLAYING:
            displaying_timer.start()
            # Start printing the currently displayed image (non-blocking)
            try:
                from ui.current_image import get_image
                img = get_image()
                strips = ai_service.get_print_strips()
                if strips:
                    # Backend pre-rendered the thermal payload
                    printer_service.start_print_strips(strips)
                elif img is not None:
                    printer_service.start_print(img)  # local Pillow fallback
            except Exception:
                print("[MAIN] failed to start printer_service", flush=True)

        elif entered_state == State.PRINTING:
            printing_timer.start()

    # 4. Update & render
    current_screen.update(dt)
    # Render to logical buffer then rotate/blit to the actual screen
    try:
        current_screen.render(buffer)
        if ROTATE_DEGREES == 0:
            screen.blit(buffer, (0, 0))
        else:
            rotated = pygame.transform.rotate(buffer, ROTATE_DEGREES)
            rect = rotated.get_rect(center=screen.get_rect().center)
            screen.fill((0, 0, 0))
            screen.blit(rotated, rect)
    except Exception:
        # Fallback: render directly if something expects the real screen
        try:
            current_screen.render(screen)
        except Exception:
            pass
    pygame.display.flip()

pygame.quit()
