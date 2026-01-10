import re

# Minimal, deterministic blocklist for kid-safe transcription filtering.
# Keep this list short, explicit, and transparent.
BLOCKLIST_WORDS = {
    # sexual terms
    "sex",
    "sexual",
    "porn",
    "porno",
    "pornography",
    "nude",
    "naked",
    "penis",
    "vagina",
    "anal",
    "cum",
    "semen",
    "breast",
    "nipple",
    "boob",
    "xxx",
    # insults / slurs / harassment (non-exhaustive)
    "bitch",
    "slut",
    "whore",
    # violence / self-harm
    "rape",
    "raping",
    "kill",
    "murder",
    "suicide",
    "selfharm",
    "gore",
    "blood",
}

BLOCKLIST_PHRASES = {
    "kill myself",
    "kill you",
    "kill him",
    "kill her",
    "hurt myself",
    "hurt you",
    "commit suicide",
}

HINDI_EXPLICIT = {
    "चोद",
    "चूत",
    "लौड़ा",
    "गांड",
    "सेक्स",
    "बलात्कार"
}

HINGLISH_EXPLICIT = {
    "chod",
    "chut",
    "gaand",
    "loda",
    "sex"
}

def is_text_safe(text: str) -> bool:
    """Return True if text is considered safe for kids, False otherwise.

    Uses a deterministic blocklist; no external services.
    """
    if not text:
        return True

    lowered = text.lower()
    words = set(filter(None, re.split(r"[^a-z]+", lowered)))

    # Single-word matches
    for word in BLOCKLIST_WORDS:
        if word in words:
            return False

    # Phrase matches (substring)
    for phrase in BLOCKLIST_PHRASES:
        if phrase in lowered:
            return False

    return True
