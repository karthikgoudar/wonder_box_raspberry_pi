import os
import numpy as np
import pytest

from services.audio_service import AudioService


class MockModelRomanThenDeva:
    def __init__(self, deva_text):
        self.deva_text = deva_text
        self.calls = []

    def transcribe(self, path, language=None):
        # First call: auto-detect (language=None) returns romanized Hindi
        # Second call with language='hi' returns Devanagari
        self.calls.append(language)
        if language == 'hi':
            return {'text': self.deva_text, 'language': 'hi'}
        return {'text': 'Hindi mein baat kar lo', 'language': 'hi'}


class MockModelEnglish:
    def transcribe(self, path, language=None):
        return {'text': 'Make a flying car', 'language': 'en'}


def make_dummy_frames(sample_rate, channels):
    # 0.5s of silence as int16 samples
    length = max(256, int(sample_rate * 0.5))
    arr = np.zeros((length, channels), dtype=np.int16)
    return [arr]


def test_forced_hindi_retranscribe(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    svc = AudioService()
    svc._frames = make_dummy_frames(svc.sample_rate, svc.channels)
    svc._whisper_model = MockModelRomanThenDeva('हिंदी में बात कर लो')
    svc._processing = True

    svc.update()

    assert svc.get_text() == 'हिंदी में बात कर लो'
    # ensure at least one forced call happened (second call had language='hi')
    assert svc._whisper_model.calls[-1] == 'hi'


def test_english_transcription(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    svc = AudioService()
    svc._frames = make_dummy_frames(svc.sample_rate, svc.channels)
    svc._whisper_model = MockModelEnglish()
    svc._processing = True

    svc.update()

    assert svc.get_text().lower().startswith('make a flying')


def test_devanagari_returned_directly(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    svc = AudioService()

    class DirectDeva:
        def transcribe(self, path, language=None):
            return {'text': 'एक फ्लायिंग कार बनाओ', 'language': 'hi'}

    svc._frames = make_dummy_frames(svc.sample_rate, svc.channels)
    svc._whisper_model = DirectDeva()
    svc._processing = True

    svc.update()

    assert 'एक' in svc.get_text()
