import sounddevice as sd
import numpy as np
import time
import threading
from scipy.io.wavfile import write
from pathlib import Path
import sys
import gc
import re
import os
import shutil
import traceback
try:
    import whisper
except Exception:
    whisper = None


class AudioService:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.channels = 1

        self._recording = False
        self._processing = False
        self._transcribing = False

        self._frames = []
        self._start_time = None

        self._wav_path = None
        self._text = None
        self._failed = False
        self._error = None
        self._stream = None
        self._thread = None
        self._lock = threading.Lock()
        # Load Whisper model once if available
        self._whisper_model = None
        if whisper is not None:
            try:
                model_name = os.environ.get("WHISPER_MODEL", "small")
                self._whisper_model = whisper.load_model(model_name)
                try:
                    import torch
                    torch.set_num_threads(1)
                except Exception:
                    pass
                print(f"[WHISPER LOCAL] model loaded: {model_name}", flush=True)
            except Exception as e:
                self._whisper_model = None
                print(f"[WHISPER LOCAL] model load failed: {e}", flush=True)

    # ------------------------
    # Public API (UNCHANGED)
    # ------------------------
    def start_recording(self):
        self.reset()
        self._recording = True
        self._start_time = time.time()
        print(f"[AUDIO] start_recording: samplerate={self.sample_rate} channels={self.channels}", flush=True)
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
        print("[AUDIO] stop_recording: stopping stream and entering processing", flush=True)
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
        if not self._processing or self._transcribing:
            return
        
        self._transcribing = True
        print("[AUDIO] update: starting WAV write and transcription", flush=True)
        
        # Start background thread for WAV writing and transcription
        self._thread = threading.Thread(target=self._process_and_transcribe, daemon=True)
        self._thread.start()

    def _process_and_transcribe(self):
        """Background thread: write WAV and transcribe"""
        print("[AUDIO] background: finalizing WAV", flush=True)

        # Ensure recordings directory exists
        output_dir = Path("recordings")
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"[AUDIO] recordings dir ready: {output_dir.resolve()}", flush=True)
        except Exception as e:
            with self._lock:
                self._failed = True
                self._error = f"failed to create recordings dir: {e}"
            print(f"[AUDIO ERROR] cannot create recordings dir: {e}", flush=True)
            self._processing = False
            self._transcribing = False
            return

        # Guard against empty frames
        if not self._frames:
            with self._lock:
                self._failed = True
                self._error = "no audio frames captured"
            print("[AUDIO ERROR] no audio frames captured", flush=True)
            self._processing = False
            self._transcribing = False
            return

        try:
            audio = np.concatenate(self._frames, axis=0)
            audio = np.squeeze(audio)
        except Exception as e:
            with self._lock:
                self._failed = True
                self._error = f"failed to concatenate frames: {e}"
            print(f"[AUDIO ERROR] concatenation failed: {e}", flush=True)
            self._processing = False
            self._transcribing = False
            return

        # Write WAV
        try:
            self._wav_path = output_dir / f"audio_{int(time.time())}.wav"
            # Normalize / convert audio to int16 PCM for consistent WAV files
            audio_arr = np.asarray(audio)
            # Diagnostic: report raw amplitude stats
            try:
                amin = float(np.min(audio_arr))
                amax = float(np.max(audio_arr))
            except Exception:
                amin = 0.0
                amax = 0.0
            print(f"[AUDIO DEBUG] audio shape={audio_arr.shape} dtype={audio_arr.dtype} min={amin:.6f} max={amax:.6f}", flush=True)

            if np.issubdtype(audio_arr.dtype, np.floating):
                # float arrays are expected in range -1.0..1.0
                audio_clipped = np.clip(audio_arr, -1.0, 1.0)

                # If the captured audio is very quiet, amplify to a sensible peak
                peak = max(abs(audio_clipped.min()), abs(audio_clipped.max()), 1e-9)
                target_peak = 0.9
                if peak < 0.25:
                    gain = target_peak / peak
                    audio_clipped = np.clip(audio_clipped * gain, -1.0, 1.0)
                    print(f"[AUDIO DEBUG] low-volume capture: peak={peak:.6f} -> applying gain {gain:.2f}", flush=True)

                audio_int16 = (audio_clipped * 32767).astype(np.int16)
            else:
                # If already integer, cast to int16 safely
                audio_int16 = audio_arr.astype(np.int16)

            write(str(self._wav_path), self.sample_rate, audio_int16)
            print(f"[AUDIO] WAV written: {self._wav_path}", flush=True)
        except Exception as e:
            with self._lock:
                self._failed = True
                self._error = f"failed to write wav: {e}"
            print(f"[AUDIO ERROR] writing WAV failed: {e}", flush=True)
            self._processing = False
            self._transcribing = False
            return

        # --- Transcribe WAV using local Whisper model ---
        if self._whisper_model is None:
            with self._lock:
                self._failed = True
                self._error = "local Whisper model not available"
            print("[WHISPER LOCAL] model not available; cannot transcribe", flush=True)
            self._processing = False
            self._transcribing = False
            return

        try:
            # Ensure ffmpeg is on PATH
            ffmpeg_bin = os.environ.get("FFMPEG_BINARY")
            if ffmpeg_bin:
                ffmpeg_dir = os.path.dirname(ffmpeg_bin)
                if ffmpeg_dir and ffmpeg_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
            else:
                try:
                    ffpath = shutil.which("ffmpeg")
                    if ffpath:
                        ffdir = os.path.dirname(ffpath)
                        if ffdir and ffdir not in os.environ.get("PATH", ""):
                            os.environ["PATH"] = ffdir + os.pathsep + os.environ.get("PATH", "")
                except Exception:
                    pass

            result = self._whisper_model.transcribe(str(self._wav_path), task="transcribe")
            detected_lang = None
            text = None
            if isinstance(result, dict):
                text = result.get("text")
                detected_lang = result.get("language")
            elif hasattr(result, "text"):
                text = result.text
                detected_lang = getattr(result, "language", None)
            if not text:
                raise RuntimeError("no transcription text returned")
            text = text.strip()
            print(f"[WHISPER] lang={detected_lang} text={text}", flush=True)
            
            # If Hindi detected but romanized, force Hindi transcription
            if detected_lang == "hi" and not re.search(r"[\u0900-\u097F]", text):
                try:
                    forced = self._whisper_model.transcribe(str(self._wav_path), language="hi", task="transcribe")
                    if isinstance(forced, dict):
                        forced_text = forced.get("text")
                    elif hasattr(forced, "text"):
                        forced_text = forced.text
                    else:
                        forced_text = None
                    if forced_text:
                        text = forced_text.strip()
                        print("[WHISPER] forced-hi: obtained Devanagari result", flush=True)
                except Exception as e:
                    print(f"[WHISPER] forced-hi failed: {e}", flush=True)
            
            with self._lock:
                self._text = text
            
            # cleanup
            try:
                del result
                del audio
            except Exception:
                pass
            self._frames = []
            gc.collect()
        except Exception as e:
            with self._lock:
                self._failed = True
                self._error = f"local whisper transcription failed: {e}"
            print(f"[WHISPER LOCAL ERROR] {e}", flush=True)
        finally:
            self._processing = False
            self._transcribing = False

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
        # Only collect frames; avoid per-frame logs for performance and clarity
        try:
            if self._recording:
                self._frames.append(indata.copy())
        except Exception:
            pass