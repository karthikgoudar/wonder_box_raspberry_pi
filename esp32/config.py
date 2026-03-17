# ============================================================
# config.py — ESP32 Wonder Box Configuration
# ============================================================
# Fill in your credentials and pin numbers here before
# flashing to the ESP32.

IDLE_TIMEOUT_SEC = 30      # Return to idle after this many seconds on DISPLAYING screen

# Toggle AI image generation (for debugging audio only)
ENABLE_AI_IMAGE_GEN = False

# --- WiFi ---
WIFI_SSID     = "YOUR_SSID"
WIFI_PASSWORD = "YOUR_PASSWORD"

# --- OpenAI API ---
OPENAI_API_KEY = "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"

# --- GROQ API (for future use, not currently implemented) ---
GROQ_API_KEY = "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"

# --- GPIO Pin Numbers ---
# Physical button (hold to record, release to stop)
BUTTON_PIN = 13      # GPIO13 → Button → GND

# I2S Microphone (e.g. INMP441)
I2S_SCK_PIN  = 26    # Bit clock
I2S_WS_PIN   = 25    # Word select (L/R clock)
I2S_SD_PIN   = 34    # Data in (mic)

# Thermal Printer — UART2
PRINTER_TX_PIN  = 17  # ESP32 TX → Printer RX
PRINTER_RX_PIN  = 16  # ESP32 RX ← Printer TX
PRINTER_BAUD    = 9600
PRINTER_WIDTH   = 384  # pixels wide for the printer head

# SPI TFT Display (e.g. ILI9341 or ST7789, 320x240)
DISPLAY_SCK_PIN  = 18
DISPLAY_MOSI_PIN = 23
DISPLAY_MISO_PIN = 19
DISPLAY_CS_PIN   = 5
DISPLAY_DC_PIN   = 21
DISPLAY_RST_PIN  = 22
DISPLAY_WIDTH    = 320
DISPLAY_HEIGHT   = 240

# --- Audio Recording ---
SAMPLE_RATE     = 16000   # Hz
RECORD_SECONDS  = 10      # Maximum recording length

# --- Behaviour ---
PRINTER_SIMULATE = False   # Set True to skip actual printing (debug)
IDLE_TIMEOUT_SEC = 30      # Return to idle after this many seconds on DISPLAYING screen
