# ============================================================
# main.py — Wonder Box ESP32 Main Loop
# ============================================================
# Runs after boot.py has connected WiFi.
# State machine mirrors the Raspberry Pi version but uses
# cooperative polling instead of threads.
#
# States:
#   IDLE        → waiting for button press
#   LISTENING   → recording audio (I2S)
#   PROCESSING  → transcribing → generating image (blocking API calls)
#   DISPLAYING  → showing generated image, waiting for print/cancel
#   PRINTING    → sending image to thermal printer
#   ERROR       → showing error, auto-return to IDLE

import utime
import gc

from core.state_machine import StateMachine
from core.states import (
    IDLE, LISTENING, PROCESSING, DISPLAYING, PRINTING, ERROR,
)
from services.button_service  import ButtonService
from services.audio_service   import AudioService
from services.ai_service      import AIService
from services.printer_service import PrinterService
from services.display_service import DisplayService
from utils.logger import log_event
from utils.timer  import Timer
from config       import IDLE_TIMEOUT_SEC

# ---- Initialise services -----------------------------------
print("[MAIN] Wonder Box ESP32 starting")

sm       = StateMachine()
button   = ButtonService()
audio    = AudioService()
ai       = AIService()
printer  = PrinterService()
display  = DisplayService()

# ---- Timers ------------------------------------------------
listening_timer  = Timer(10.0)    # max recording length
displaying_timer = Timer(float(IDLE_TIMEOUT_SEC))

# ---- State helpers -----------------------------------------
ai_started = False

def enter_idle():
    global ai_started
    audio.reset()
    ai.reset()
    printer.reset()
    ai_started = False
    display.show_idle()
    sm.transition(IDLE, reason="enter_idle")

def enter_listening():
    audio.reset()
    ai.reset()
    audio.start_recording()
    listening_timer.start()
    display.show_listening()
    sm.transition(LISTENING, reason="button pressed")

def enter_processing():
    audio.stop_recording()
    display.show_processing(0)
    sm.transition(PROCESSING, reason="button released")

def enter_displaying():
    global ai_started
    ai_started = False
    displaying_timer.start()
    image_bytes = ai.get_image_bytes()
    if image_bytes:
        display.show_image(image_bytes)
    else:
        display.show_error("No image")
    sm.transition(DISPLAYING, reason="generation complete")

def enter_printing():
    display.show_printing()
    sm.transition(PRINTING, reason="print approved")

def enter_error(reason="Unknown error"):
    display.show_error(reason)
    sm.transition(ERROR, reason=reason)

# ---- Initial screen ----------------------------------------
display.show_idle()
log_event("MAIN", "READY")
print("[MAIN] ready — hold button to record")

# ============================================================
# Main loop
# ============================================================
while True:
    state = sm.get_state()

    # ---- Button polling ------------------------------------
    pressed_edge, released_edge = button.update()

    # ========================================================
    # IDLE
    # ========================================================
    if state == IDLE:
        if pressed_edge:
            enter_listening()

    # ========================================================
    # LISTENING — fill audio buffer every loop tick
    # ========================================================
    elif state == LISTENING:
        # Fill I2S audio buffer
        buf_full = not audio.read_chunk()

        # Cancel if button released
        if released_edge:
            enter_processing()

        # Auto-stop if max duration reached or buffer full
        elif buf_full or listening_timer.is_finished():
            print("[MAIN] listening stopped (timeout or buffer full)")
            enter_processing()

    # ========================================================
    # PROCESSING — transcribe audio, then generate image
    # ========================================================
    elif state == PROCESSING:
        dots = display.update_dots()
        display.show_processing(dots)

        # --- Step 1: audio transcription (blocking) ----------
        if not audio.is_done() and not audio.has_failed():
            audio.update()   # blocking ~2-5 sec on first call

        elif audio.has_failed():
            enter_error("Transcription failed: " + str(audio.get_error()))

        # --- Step 2: AI image generation (blocking) ----------
        elif audio.is_done() and not ai_started:
            text = audio.get_text()
            print("[MAIN] transcribed:", text)
            ai.start_generation(text)
            ai_started = True

        elif ai_started and not ai.is_done() and not ai.has_failed():
            ai.update()      # blocking ~5-15 sec on first call

        elif ai.has_failed():
            enter_error("Image gen failed: " + str(ai.get_error()))

        elif ai.is_done():
            enter_displaying()

        gc.collect()

    # ========================================================
    # DISPLAYING — show image, wait for print or timeout
    # ========================================================
    elif state == DISPLAYING:
        # Button press → print
        if pressed_edge:
            enter_printing()

        # Auto-return to idle after timeout
        elif displaying_timer.is_finished():
            enter_printing()
            print("[MAIN] display timeout, returning to idle")
            enter_idle()

    # ========================================================
    # PRINTING — send image to printer, then return to idle
    # ========================================================
    elif state == PRINTING:
        image_bytes = ai.get_image_bytes()

        if image_bytes and not printer.is_done() and not printer.has_failed():
            printer.print_image(image_bytes)  # blocking

        elif printer.has_failed():
            enter_error("Print failed: " + str(printer.get_error()))

        elif printer.is_done():
            utime.sleep_ms(500)
            enter_idle()

    # ========================================================
    # ERROR — show for 5 seconds then return to idle
    # ========================================================
    elif state == ERROR:
        utime.sleep_ms(5000)
        enter_idle()

    # Small yield to prevent watchdog issues
    utime.sleep_ms(10)
