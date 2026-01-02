import sounddevice as sd
import numpy as np
import time
from scipy.io.wavfile import write
from pathlib import Path
import sys


class AudioService:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.channels = 1

        self._recording = False
        self._processing = False

        self._frames = []
        self._start_time = None

        self._wav_path = None
        self._text = None  # still stub
        self._failed = False
        self._error = None
        self._stream = None

    # ------------------------
    # Public API (UNCHANGED)
    # ------------------------
    def start_recording(self):
        self.reset()
        self._recording = True
        self._start_time = time.time()
        print(f"[AUDIO] start_recording() samplerate={self.sample_rate} channels={self.channels}", flush=True)
        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=self._audio_callback
            )
            self._stream.start()
            print("[AUDIO] InputStream started", flush=True)
        except Exception as e:
            # Likely permission or device error
            self._failed = True
            self._error = f"start_recording failed: {e}"
            print(f"[AUDIO ERROR] start_recording exception: {e}", flush=True)

    def stop_recording(self):
        if not self._recording:
            return

        self._recording = False
        self._processing = True
        print("[AUDIO] stop_recording() called — stopping stream and entering processing", flush=True)
        # Ensure stream is stopped/closed promptly
        try:
            if self._stream is not None:
                try:
                    self._stream.stop()
                except Exception:
                    pass
                try:
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
                print("[AUDIO] InputStream stopped and closed", flush=True)
        except Exception as e:
            print(f"[AUDIO ERROR] stopping stream: {e}", flush=True)

    def update(self):
        if not self._processing:
            return
        print("[AUDIO] update() entering processing — finalizing WAV", flush=True)

        # Ensure recordings directory exists
        output_dir = Path("recordings")
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"[AUDIO] recordings dir ready: {output_dir.resolve()}", flush=True)
        except Exception as e:
            self._failed = True
            self._error = f"failed to create recordings dir: {e}"
            print(f"[AUDIO ERROR] cannot create recordings dir: {e}", flush=True)
            self._processing = False
            return

        # Guard against empty frames
        if not self._frames:
            self._failed = True
            self._error = "no audio frames captured"
            print("[AUDIO ERROR] no audio frames captured — nothing to write", flush=True)
            self._processing = False
            return

        try:
            audio = np.concatenate(self._frames, axis=0)
            audio = np.squeeze(audio)
        except Exception as e:
            self._failed = True
            self._error = f"failed to concatenate frames: {e}"
            print(f"[AUDIO ERROR] concatenation failed: {e}", flush=True)
            self._processing = False
            return

        # Write WAV
        try:
            self._wav_path = output_dir / f"audio_{int(time.time())}.wav"
            write(str(self._wav_path), self.sample_rate, audio)
            print(f"[AUDIO] WAV written: {self._wav_path}", flush=True)
        except Exception as e:
            self._failed = True
            self._error = f"failed to write wav: {e}"
            print(f"[AUDIO ERROR] writing WAV failed: {e}", flush=True)
            self._processing = False
            return

        # Stub text (unchanged for now)
        self._text = "Draw a flying dragon"

        self._processing = False

    def is_done(self):
        return self._text is not None

    def has_failed(self):
        return self._failed

    def get_text(self):
        return self._text

    def get_error(self):
        return self._error

    def reset(self):
        self._recording = False
        self._processing = False
        self._frames = []
        self._wav_path = None
        self._text = None
        self._failed = False
        self._error = None
        # ensure any existing stream is closed
        try:
            if getattr(self, '_stream', None) is not None:
                try:
                    self._stream.stop()
                except Exception:
                    pass
                try:
                    self._stream.close()
                except Exception:
                    pass
        except Exception:
            pass
        self._stream = None

    # ------------------------
    # Internal callback
    # ------------------------
    def _audio_callback(self, indata, frames, time_info, status):
        # This callback is invoked in the sounddevice thread — keep it minimal.
        try:
            if status:
                # report overrun/underrun or other issues
                print(f"[AUDIO CALLBACK] status: {status}", flush=True)

            if self._recording:
                # indata is a numpy array shape (frames, channels)
                self._frames.append(indata.copy())
                # log that we got data (count only, to avoid flooding)
                if len(self._frames) % 50 == 0:
                    print(f"[AUDIO CALLBACK] frames buffer size={len(self._frames)}", flush=True)
        except Exception as e:
            # Avoid raising in callback
            try:
                print(f"[AUDIO CALLBACK ERROR] {e}", flush=True)
            except Exception:
                pass