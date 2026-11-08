import sounddevice as sd
import numpy as np
import time
import threading
from scipy.io.wavfile import write
from pathlib import Path
import gc
import os
import shutil

class AudioService:
    def __init__(self, sample_rate=44100, device=None):
        # Force 44.1kHz sample rate and store explicit device index for Raspberry Pi USB mic
        # `device` is the integer index reported by sd.query_devices()
        self.sample_rate = sample_rate
        # Force mono input
        self.channels = 1
        # ALSA device string (explicit USB microphone device)
        # Audio input device index. Set AUDIO_DEVICE in .env if the default is wrong
        # (list devices with: python -c "import sounddevice as sd; print(sd.query_devices())")
        if device is None:
            device = int(os.getenv("AUDIO_DEVICE", "1"))
        self.device = device
        # Hardware-free testing: if AUDIO_TEST_WAV points at a WAV file, use it
        # instead of the microphone.
        self.test_wav = os.getenv("AUDIO_TEST_WAV") or None

        self._recording = False
        self._processing = False
        self._saving = False

        self._frames = []
        self._wav_path = None
        self._done = False
        self._failed = False
        self._error = None
        self._stream = None
        self._thread = None
        self._lock = threading.Lock()

    # ------------------------
    # Public API
    # ------------------------

    def start_recording(self):
        self.reset()
        self._recording = True
        if self.test_wav:
            print(f"[AUDIO] AUDIO_TEST_WAV set; not opening the microphone", flush=True)
            return
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
                time.sleep(0.05)  # allow final callback delivery on Raspberry Pi
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass

        self._stream = None

    def update(self):
        if not self._processing or self._saving:
            return

        self._saving = True
        self._thread = threading.Thread(target=self._process_and_save, daemon=True)
        self._thread.start()

    # ------------------------
    # Background processing
    # ------------------------

    def _process_and_save(self):
        try:
            output_dir = Path("recordings")
            output_dir.mkdir(parents=True, exist_ok=True)

            if self.test_wav:
                src = Path(self.test_wav)
                if not src.is_file():
                    raise RuntimeError(f"AUDIO_TEST_WAV not found: {src}")
                self._wav_path = output_dir / f"audio_{int(time.time())}.wav"
                shutil.copyfile(src, self._wav_path)
                print(f"[AUDIO] using test WAV {src}", flush=True)
                with self._lock:
                    self._done = True
                return

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

            # Transcription now happens in the cloud backend (see ai_service).
            print(f"[AUDIO] saved {self._wav_path}", flush=True)
            with self._lock:
                self._done = True

        except Exception as e:
            with self._lock:
                self._failed = True
                self._error = str(e)

        finally:
            self._frames.clear()
            gc.collect()
            self._processing = False
            self._saving = False

    # ------------------------
    # Status API
    # ------------------------

    def is_done(self):
        """True once the WAV file has been written and is ready to upload."""
        with self._lock:
            return self._done

    def has_failed(self):
        with self._lock:
            return self._failed

    def get_wav_path(self):
        """Path of the recorded WAV (str), or None until is_done()."""
        with self._lock:
            return str(self._wav_path) if self._done and self._wav_path else None

    def get_error(self):
        with self._lock:
            return self._error

    def reset(self):
        self._recording = False
        self._processing = False
        self._saving = False
        self._frames.clear()
        self._wav_path = None
        self._done = False
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
        if status:
            print("Audio status:", status, flush=True)

        # Always collect frames while stream is active (avoid race on Raspberry Pi)
        self._frames.append(indata.copy())
