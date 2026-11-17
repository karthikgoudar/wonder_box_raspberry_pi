import sounddevice as sd
import numpy as np
import time
import threading
from scipy.io.wavfile import write
from pathlib import Path
import gc
import os
import shutil

def _device_from_env():
    """AUDIO_DEVICE may be a device index ("1") or part of its name ("voicehat").

    Unset means the system default input. List devices with:
    python -c "import sounddevice as sd; print(sd.query_devices())"
    """
    raw = (os.getenv("AUDIO_DEVICE") or "").strip()
    if not raw:
        return None
    return int(raw) if raw.lstrip("-").isdigit() else raw


class AudioService:
    def __init__(self, sample_rate=None, device=None):
        # The I2S microphone (INMP441 via the googlevoicehat driver) only runs at
        # 48 kHz, so that is the default. Override with AUDIO_SAMPLE_RATE.
        self.sample_rate = sample_rate or int(os.getenv("AUDIO_SAMPLE_RATE", "48000"))
        # Channels to open. The I2S microphone is stereo hardware with the mic on
        # one side (L/R pin tied to ground = left), so open 2 and keep
        # AUDIO_MIC_CHANNEL (0 = left). The saved WAV is always mono.
        self.channels = int(os.getenv("AUDIO_CHANNELS", "1"))
        self.mic_channel = int(os.getenv("AUDIO_MIC_CHANNEL", "0"))
        # Quiet microphones are boosted so the loudest moment reaches 90%, but
        # never by more than AUDIO_MAX_GAIN times (so silence is not blown up).
        self.max_gain = float(os.getenv("AUDIO_MAX_GAIN", "40"))
        # The saved WAV is shrunk to this rate before upload. Speech needs no
        # more than 16 kHz, and a 3x smaller file made speech-to-text about
        # 1 s instead of 4.6-9 s in 17 Nov tests. 0 keeps the recording rate.
        self.save_rate = int(os.getenv("AUDIO_SAVE_RATE", "16000"))
        self.device = device if device is not None else _device_from_env()
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
            # Record as floating point so a quiet microphone keeps its detail
            # before the boost. Use a non-zero blocksize so callbacks deliver
            # frames predictably on Raspberry Pi.
            self._stream = sd.InputStream(
                device=self.device,
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='float32',
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

            audio = np.concatenate(self._frames, axis=0)
            if audio.ndim == 2:
                # Keep only the channel the microphone is on
                ch = min(self.mic_channel, audio.shape[1] - 1)
                audio = audio[:, ch]

            audio, rate = self._downsample(audio)
            self._wav_path = output_dir / f"audio_{int(time.time())}.wav"
            audio_int16 = self._boost_to_int16(audio)

            write(str(self._wav_path), rate, audio_int16)

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

    def _downsample(self, audio):
        """Lower the sample rate to AUDIO_SAVE_RATE (filtered, so no hiss)."""
        target = self.save_rate
        if not target or target >= self.sample_rate:
            return audio, self.sample_rate
        from math import gcd
        from scipy.signal import resample_poly  # imported here: slow to load
        g = gcd(self.sample_rate, target)
        if np.issubdtype(audio.dtype, np.integer):
            audio = audio.astype(np.float32) / np.iinfo(audio.dtype).max
        out = resample_poly(audio.astype(np.float32), target // g, self.sample_rate // g)
        return out.astype(np.float32), target

    def _boost_to_int16(self, audio):
        """Remove any constant offset, boost quiet audio, return 16-bit samples."""
        if np.issubdtype(audio.dtype, np.integer):
            audio = audio.astype(np.float32) / np.iinfo(audio.dtype).max
        audio = audio.astype(np.float32)
        if audio.size:
            audio = audio - float(np.mean(audio))
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if 0.0 < peak < 0.9:
            audio = audio * min(0.9 / peak, self.max_gain)
        return (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)

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
