import sounddevice as sd
import numpy as np
import time
import threading
from scipy.io.wavfile import write
from pathlib import Path
import re
import os

try:
    import whisper
except Exception:
    whisper = None


class AudioService:
    def __init__(self, sample_rate=44100, device=1):
        # Force 44.1kHz sample rate and store explicit device index for Raspberry Pi USB mic
        # `device` is the integer index reported by sd.query_devices()
        self.sample_rate = sample_rate
        # Force mono input
        self.channels = 1
        # ALSA device string (explicit USB microphone device)
        self.device = device

        self._recording = False
        self._processing = False
        self._transcribing = False

        self._frames = []
        self._wav_path = None
        self._text = None
        self._failed = False
        self._error = None
        self._stream = None
        self._thread = None
        self._lock = threading.Lock()

        self._whisper_model = None

        if whisper is not None:
            try:
                print("[WHISPER] loading model...", flush=True)
                self._whisper_model = whisper.load_model("tiny")

                try:
                    import torch
                    torch.set_num_threads(1)
                except Exception:
                    pass

                print("[WHISPER] model loaded: small", flush=True)

            except Exception as e:
                print(f"[WHISPER] model load failed: {e}", flush=True)
                self._whisper_model = None

    # ------------------------
    # Public API
    # ------------------------

    def start_recording(self):
        self.reset()
        self._recording = True
        try:
            # Open the device by integer index (e.g. `1`), force 44.1kHz, mono, 16-bit PCM
            # Use a non-zero blocksize so callbacks deliver frames predictably on Raspberry Pi
            self._stream = sd.InputStream(
                device=self.device,
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='int16',
                blocksize=1024,
                callback=self._audio_callback
            )
            # Explicitly start the stream to ensure callbacks begin
            self._stream.start()
        except Exception as e:
            # Fail gracefully: record error state and avoid raising to caller/state machine
            self._stream = None
            self._failed = True
            self._error = f"start_recording failed: {e}"
            # ensure state machine isn't left thinking recording is active
            self._recording = False
            return

    def stop_recording(self):
        if not self._recording:
            return
        self._recording = False
        self._processing = True

        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass

        self._stream = None

    def update(self):
        if not self._processing or self._transcribing:
            return

        self._transcribing = True
        self._thread = threading.Thread(target=self._process_and_transcribe, daemon=True)
        self._thread.start()

    # ------------------------
    # Background processing
    # ------------------------

    def _process_and_transcribe(self):
        try:
            output_dir = Path("recordings")
            output_dir.mkdir(parents=True, exist_ok=True)

            if not self._frames:
                raise RuntimeError("no audio frames captured")

            audio = np.concatenate(self._frames, axis=0).squeeze()

            self._wav_path = output_dir / f"audio_{int(time.time())}.wav"

            if np.issubdtype(audio.dtype, np.floating):
                audio = np.clip(audio, -1.0, 1.0)
                peak = max(abs(audio.min()), abs(audio.max()), 1e-9)
                if peak < 0.25:
                    audio = np.clip(audio * (0.9 / peak), -1.0, 1.0)
                audio_int16 = (audio * 32767).astype(np.int16)
            else:
                audio_int16 = audio.astype(np.int16)

            write(str(self._wav_path), self.sample_rate, audio_int16)

            if not self._whisper_model:
                raise RuntimeError("Whisper model not loaded")

            # Single transcription call with auto language detection
            result = self._whisper_model.transcribe(
                str(self._wav_path),
                task="transcribe",
                temperature=0,
                fp16=False
            )

            text = result.get("text", "").strip()
            lang = result.get("language", "unknown")
            print(f"[WHISPER] lang={lang} text={text}", flush=True)

            if not text:
                raise RuntimeError("empty transcription")

            with self._lock:
                self._text = text

        except Exception as e:
            with self._lock:
                self._failed = True
                self._error = str(e)

        finally:
            self._frames.clear()
            gc.collect()
            self._processing = False
            self._transcribing = False

    # ------------------------
    # Status API
    # ------------------------

    def is_done(self):
        with self._lock:
            return self._text is not None

    def has_failed(self):
        with self._lock:
            return self._failed

    def get_text(self):
        with self._lock:
            return self._text

    def get_error(self):
        with self._lock:
            return self._error

    def reset(self):
        self._recording = False
        self._processing = False
        self._transcribing = False
        self._frames.clear()
        self._wav_path = None
        self._text = None
        self._failed = False
        self._error = None

        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass

        self._stream = None

    # ------------------------
    # Audio callback
    # ------------------------

    def _audio_callback(self, indata, frames, time_info, status):
        if self._recording:
            self._frames.append(indata.copy())
