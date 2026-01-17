import os, traceback
model = os.environ.get("WHISPER_MODEL", "tiny")
print("Attempting to load Whisper model:", model)
try:
    import whisper
    whisper.load_model(model)
    print(" model loaded")
except Exception:
    traceback.print_exc()
