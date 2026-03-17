# ============================================================
# services/audio_service.py — I2S Recording + OpenAI Whisper
# ============================================================
# Hardware: INMP441 (or similar I2S MEMS microphone)
# Wiring (default pins in config.py):
#   SCK  → I2S Bit Clock
#   WS   → I2S Word Select
#   SD   → I2S Data (mic output)
#   L/R  → GND  (select LEFT channel)
#
# Flow:
#   1. start_recording()  — starts filling buffer via I2S
#   2. stop_recording()   — stops I2S, marks buffer ready
#   3. update()           — called every loop; triggers transcription
#                           when buffer is ready (blocking HTTP call)
#   4. is_done()          — True when text is available
#   5. get_text()         — returns the transcribed string

import utime
import ujson
import ubinascii
import gc

from machine import I2S, Pin
import urequests

from config import (
    OPENAI_API_KEY,
    GROQ_API_KEY,
    SAMPLE_RATE, RECORD_SECONDS,
    I2S_SCK_PIN, I2S_WS_PIN, I2S_SD_PIN,
)

# Maximum samples to capture (16-bit mono)
_MAX_SAMPLES = SAMPLE_RATE * RECORD_SECONDS
_BUFFER_BYTES = _MAX_SAMPLES * 2  # 2 bytes per int16 sample


class AudioService:
    def __init__(self):
        self.sample_rate = SAMPLE_RATE
        self._recording  = False
        self._processing = False
        self._transcribing = False
        self._text   = None
        self._failed = False
        self._error  = None
        self._i2s    = None
        # Pre-allocate recording buffer to avoid fragmentation
        self._buf    = bytearray(_BUFFER_BYTES)
        self._bytes_recorded = 0

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def start_recording(self):
        self.reset()
        self._recording = True
        self._bytes_recorded = 0

        try:
            self._i2s = I2S(
                0,
                sck=Pin(I2S_SCK_PIN),
                ws=Pin(I2S_WS_PIN),
                sd=Pin(I2S_SD_PIN),
                mode=I2S.RX,
                bits=16,
                format=I2S.MONO,
                rate=self.sample_rate,
                ibuf=4096,
            )
            print("[AudioService] recording started")
        except Exception as e:
            self._failed = True
            self._error  = "I2S init failed: " + str(e)
            print("[AudioService ERROR]", self._error)

    def read_chunk(self):
        """
        Call this every loop while recording to fill the buffer.
        Returns False when the buffer is full (max duration reached).
        """
        if not self._recording or self._i2s is None:
            return False

        chunk_size = 512  # bytes per read
        remaining  = _BUFFER_BYTES - self._bytes_recorded
        if remaining <= 0:
            return False  # buffer full → auto-stop

        read_size = min(chunk_size, remaining)
        view = memoryview(self._buf)[self._bytes_recorded:self._bytes_recorded + read_size]
        num_read = self._i2s.readinto(view)
        self._bytes_recorded += num_read
        return True

    def stop_recording(self):
        if not self._recording:
            return
        self._recording = False

        if self._i2s:
            try:
                self._i2s.deinit()
            except Exception:
                pass
            self._i2s = None

        self._processing = True
        print("[AudioService] recording stopped,", self._bytes_recorded, "bytes captured")

    def update(self):
        """
        Call every loop. When processing is flagged, performs the
        HTTP transcription request (blocking — expect ~2-5 sec).
        No threading on ESP32; use in a cooperative loop.
        """
        if not self._processing or self._transcribing:
            return

        self._transcribing = True
        self._transcribe()

    # --------------------------------------------------------
    # Transcription (blocking HTTP call to OpenAI Whisper)
    # --------------------------------------------------------

    def _transcribe(self):
        audio_bytes = None  # declared here so finally block can safely reference it
        try:
            if self._bytes_recorded == 0:
                raise RuntimeError("no audio captured")

            audio_bytes = bytes(self._buf[:self._bytes_recorded])

            # Wrap raw PCM in a minimal WAV container
            wav_data = self._make_wav(audio_bytes, self.sample_rate, 1, 16)

            print("[AudioService] sending", len(wav_data), "bytes to Whisper API")

            # --- DEBUG: save WAV locally so we can inspect audio later ---
            try:
                ts = utime.ticks_ms()
                fname = "recording_%d.wav" % ts 
                with open(fname, "wb") as f:
                    f.write(wav_data)
                print("[AudioService] saved debug WAV to", fname)
            except Exception as e:
                print("[AudioService] failed to save debug WAV:", e)
            # --- end DEBUG block ---
            
            # Build multipart/form-data body manually
            boundary = "WonderBoxBoundary"
            body = (
                "--" + boundary + "\r\n"
                "Content-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-1\r\n"
                "--" + boundary + "\r\n"
                "Content-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\n"
                "Content-Type: audio/wav\r\n\r\n"
            ).encode() + wav_data + (
                "\r\n--" + boundary + "--\r\n"
            ).encode()

            headers = {
                "Authorization": "Bearer " + OPENAI_API_KEY,
                "Content-Type": "multipart/form-data; boundary=" + boundary,
                "Content-Length": str(len(body)),
            }

            resp = urequests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",  # ← swap URL
                    headers={
                    "Authorization": "Bearer " + GROQ_API_KEY,  # ← swap key
                    "Content-Type": "multipart/form-data; boundary=" + boundary,
                    "Content-Length": str(len(body)),
                    },
                    data=body,
            )
            if resp.status_code != 200:
                resp = urequests.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers=headers,
                    data=body,
                )

                if resp.status_code != 200:
                    raise RuntimeError("Whisper API error " + str(resp.status_code))

            data = ujson.loads(resp.text)
            resp.close()

            text = data.get("text", "").strip()
            if not text:
                raise RuntimeError("empty transcription")

            # Clean up for kids UX
            text = text.replace(".", "").strip()
            text = text[0].upper() + text[1:] if text else text

            print("[AudioService] transcribed:", text)
            self._text = text

        except Exception as e:
            self._failed = True
            self._error  = str(e)
            print("[AudioService ERROR]", self._error)
        finally:
            # Free the buffer copy (audio_bytes may be None if recording was empty)
            if audio_bytes is not None:
                del audio_bytes
            gc.collect()
            self._processing   = False
            self._transcribing = False

    # --------------------------------------------------------
    # WAV header builder (no external libraries needed)
    # --------------------------------------------------------

    @staticmethod
    def _make_wav(pcm_bytes, sample_rate, num_channels, bits_per_sample):
        data_size   = len(pcm_bytes)
        byte_rate   = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8

        header = bytearray(44)
        # RIFF chunk descriptor
        header[0:4]   = b'RIFF'
        header[4:8]   = (data_size + 36).to_bytes(4, 'little')
        header[8:12]  = b'WAVE'
        # fmt sub-chunk
        header[12:16] = b'fmt '
        header[16:20] = (16).to_bytes(4, 'little')       # subchunk1 size
        header[20:22] = (1).to_bytes(2, 'little')         # PCM format
        header[22:24] = num_channels.to_bytes(2, 'little')
        header[24:28] = sample_rate.to_bytes(4, 'little')
        header[28:32] = byte_rate.to_bytes(4, 'little')
        header[32:34] = block_align.to_bytes(2, 'little')
        header[34:36] = bits_per_sample.to_bytes(2, 'little')
        # data sub-chunk
        header[36:40] = b'data'
        header[40:44] = data_size.to_bytes(4, 'little')
        return bytes(header) + pcm_bytes

    # --------------------------------------------------------
    # Status API
    # --------------------------------------------------------

    def is_done(self):
        return self._text is not None

    def has_failed(self):
        return self._failed

    def get_text(self):
        return self._text

    def get_error(self):
        return self._error

    def is_recording(self):
        return self._recording

    def reset(self):
        self._recording    = False
        self._processing   = False
        self._transcribing = False
        self._text         = None
        self._failed       = False
        self._error        = None
        self._bytes_recorded = 0
        if self._i2s:
            try:
                self._i2s.deinit()
            except Exception:
                pass
            self._i2s = None
