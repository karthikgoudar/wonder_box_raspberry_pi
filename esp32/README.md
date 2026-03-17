# Wonder Box — ESP32 Port

This folder contains the MicroPython port of the Wonder Box project for the **ESP32** microcontroller.

---

## Hardware Requirements

| Component | Details |
|---|---|
| ESP32 board | ESP32-WROVER (with PSRAM) recommended; standard ESP32 works with smaller images |
| Microphone | INMP441 I2S MEMS microphone |
| Display | ILI9341 320×240 SPI TFT (or ST7789 240×240) |
| Thermal Printer | ESC/POS compatible (e.g. RP203), connected via UART |
| Button | Momentary push button, GPIO → GND |

---

## Pin Wiring

Edit `config.py` to match your actual wiring:

| Signal | Default GPIO |
|---|---|
| Button | GPIO 13 |
| I2S SCK (mic) | GPIO 26 |
| I2S WS (mic) | GPIO 25 |
| I2S SD (mic) | GPIO 34 |
| Display SCK | GPIO 18 |
| Display MOSI | GPIO 23 |
| Display MISO | GPIO 19 |
| Display CS | GPIO 5 |
| Display DC | GPIO 21 |
| Display RST | GPIO 22 |
| Printer TX | GPIO 17 |
| Printer RX | GPIO 16 |

---

## Setup Steps

### 1. Flash MicroPython
Download the latest MicroPython firmware for ESP32 from https://micropython.org/download/esp32/ and flash it:

```
esptool.py --port COM_PORT erase_flash
esptool.py --port COM_PORT write_flash -z 0x1000 esp32-firmware.bin
```

### 2. Install the ILI9341 display driver
Connect to the REPL and run:

```python
import mip
mip.install("github:rdagger/micropython-ili9341")
```

### 3. Configure credentials
Edit `config.py` and fill in:
- `WIFI_SSID` and `WIFI_PASSWORD`
- `OPENAI_API_KEY`
- Verify pin numbers match your wiring

### 4. Upload files
Use `mpremote`, `Thonny`, or `rshell` to copy files to the ESP32:

```
mpremote cp -r esp32/ :
```

Or individually:
```
mpremote cp esp32/boot.py :boot.py
mpremote cp esp32/main.py :main.py
mpremote cp esp32/config.py :config.py
mpremote mkdir :core
mpremote cp esp32/core/states.py :core/states.py
mpremote cp esp32/core/state_machine.py :core/state_machine.py
mpremote mkdir :services
mpremote cp esp32/services/audio_service.py :services/audio_service.py
mpremote cp esp32/services/ai_service.py :services/ai_service.py
mpremote cp esp32/services/printer_service.py :services/printer_service.py
mpremote cp esp32/services/button_service.py :services/button_service.py
mpremote cp esp32/services/display_service.py :services/display_service.py
mpremote mkdir :utils
mpremote cp esp32/utils/logger.py :utils/logger.py
mpremote cp esp32/utils/timer.py :utils/timer.py
```

### 5. Reset and run
Press the ESP32 reset button. `boot.py` will connect to WiFi, then `main.py` will start the Wonder Box loop.

---

## Architecture

```
boot.py              WiFi connection + NTP sync
main.py              Main FSM loop (cooperative polling, no threads)
config.py            All pins, credentials, and settings

core/
  states.py          State constants (IDLE, LISTENING, etc.)
  state_machine.py   State machine with logging

services/
  button_service.py  GPIO button with debounce
  audio_service.py   I2S microphone recording + OpenAI Whisper API
  ai_service.py      OpenAI DALL-E image generation
  printer_service.py ESC/POS thermal printer via UART
  display_service.py ILI9341 TFT display

utils/
  logger.py          Serial console logger
  timer.py           Simple countdown timer using utime
```

---

## Key Differences from Raspberry Pi Version

| Feature | Raspberry Pi | ESP32 |
|---|---|---|
| Language runtime | CPython 3.x | MicroPython |
| UI | pygame (600×600) | ILI9341 TFT (320×240) |
| Audio capture | sounddevice + numpy | machine.I2S (raw PCM) |
| Threading | threading.Thread | Cooperative loop (blocking calls) |
| OpenAI SDK | `openai` Python package | Raw HTTP via `urequests` |
| Image processing | PIL + numpy | Pure MicroPython PNG decoder |
| GPIO | gpiozero / lgpio | machine.Pin |
| Serial | pyserial | machine.UART |
| Env vars | .env + python-dotenv | config.py constants |
| Logging | JSON files on disk | Serial console |

---

## Memory Notes

- **Standard ESP32 (520 KB RAM):** Use `IMAGE_SIZE = "256x256"` in `ai_service.py` to keep image buffers within limits.
- **ESP32-WROVER (4 MB PSRAM):** Can handle `"512x512"` or larger images.
- Run `gc.collect()` frequently; MicroPython's heap is much smaller than CPython's.

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| WiFi not connecting | Wrong credentials | Check `WIFI_SSID` / `WIFI_PASSWORD` in config.py |
| `MemoryError` | Image too large | Reduce `IMAGE_SIZE` in `ai_service.py` |
| No audio captured | Wrong I2S pins | Verify `I2S_SCK_PIN`, `I2S_WS_PIN`, `I2S_SD_PIN` |
| Display blank | Wrong SPI pins or driver not installed | Check wiring and install ili9341 driver |
| Printer not printing | Wrong UART pins or baud rate | Verify `PRINTER_TX_PIN`, `PRINTER_BAUD` |
| `ImportError: ili9341` | Driver not installed | Run `mip.install("github:rdagger/micropython-ili9341")` |
