"""Story folders, the story player, story requests and the button light."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from core.states import State
from services import story_library as lib
from services.story_player import StoryPlayer, _sentence_at


@pytest.fixture(autouse=True)
def _pygame():
    pygame.init()
    yield


def make_story(root, lang="en", name="01_test", scenes=(("0:00", "One. Two."), ("0:20", "Three.")),
               sticker=False, skip=()):
    folder = root / lang / name
    (folder / "images").mkdir(parents=True)
    (folder / "text").mkdir()
    if "title" not in skip:
        (folder / "title.txt").write_text("ಆನೆ ಮತ್ತು ಇಲಿ\nThe Elephant and the Mouse\n", encoding="utf-8")
    if "audio" not in skip:
        (folder / "story.mp3").write_bytes(b"ID3fake")
    lines = []
    for i, (t, words) in enumerate(scenes, 1):
        stem = f"scene_{i:02d}"
        lines.append(f"{stem} {t}")
        if f"image{i}" not in skip:
            pygame.image.save(pygame.Surface((40, 30)), str(folder / "images" / f"{stem}.png"))
        (folder / "text" / f"{stem}.txt").write_text(words, encoding="utf-8")
    if "timings" not in skip:
        (folder / "timings.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if sticker:
        pygame.image.save(pygame.Surface((40, 30)), str(folder / "images" / "sticker.png"))
    return folder


# ── Library ──────────────────────────────────────────────────────────────────

def test_parse_time():
    assert lib.parse_time("0:00") == 0
    assert lib.parse_time("0:18.5") == 18.5
    assert lib.parse_time("1:02") == 62
    assert lib.parse_time("41") == 41
    for bad in ("", "a:b", "1::2", "-3"):
        with pytest.raises(ValueError):
            lib.parse_time(bad)


def test_sentences_split_in_all_three_languages():
    assert lib.split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]
    assert lib.split_sentences("ಆನೆ ಬಂತು. ಇಲಿ ಓಡಿತು.") == ["ಆನೆ ಬಂತು.", "ಇಲಿ ಓಡಿತು."]
    assert lib.split_sentences("हाथी आया। चूहा भागा।") == ["हाथी आया।", "चूहा भागा।"]


def test_load_story(tmp_path):
    story = lib.load_story(make_story(tmp_path, "kn", sticker=True))
    assert story.language == "kn" and story.name == "kn/01_test"
    assert (story.title, story.title_en) == ("ಆನೆ ಮತ್ತು ಇಲಿ", "The Elephant and the Mouse")
    assert [s.start for s in story.scenes] == [0, 20]
    assert story.scenes[0].sentences == ["One.", "Two."]
    assert story.scenes[1].image.name == "scene_02.png"
    assert story.sticker.name == "sticker.png"


@pytest.mark.parametrize("skip,message", [
    (("audio",), "story.mp3 is missing"),
    (("timings",), "timings.txt is missing"),
    (("image2",), "images/scene_02.png is missing"),
    (("title",), "title.txt is missing"),
])
def test_missing_files_are_named(tmp_path, skip, message):
    with pytest.raises(lib.StoryError, match=message.replace(".", r"\.")):
        lib.load_story(make_story(tmp_path, skip=skip))


def test_bad_timings_are_explained(tmp_path):
    folder = make_story(tmp_path)
    (folder / "timings.txt").write_text("scene_01 0:00\nscene_02 zero\n")
    with pytest.raises(lib.StoryError, match="not a time"):
        lib.load_story(folder)
    (folder / "timings.txt").write_text("scene_01 0:00\nscene_02 0:20\nscene_03 0:10\n")
    with pytest.raises(lib.StoryError, match="must go up"):
        lib.load_story(folder)


def test_picker_takes_turns_and_falls_back_to_english(tmp_path):
    make_story(tmp_path, "kn", "01_a")
    make_story(tmp_path, "kn", "02_b")
    make_story(tmp_path, "en", "01_c")
    make_story(tmp_path, "kn", "03_broken", skip=("audio",))
    picker = lib.StoryPicker(tmp_path)
    assert [picker.pick("kn").folder.name for _ in range(3)] == ["01_a", "02_b", "01_a"]
    assert picker.pick("hi").name == "en/01_c"   # no Hindi story yet
    assert lib.StoryPicker(tmp_path / "empty").pick("en") is None


def test_checker_reports_problems(tmp_path, capsys):
    make_story(tmp_path, "en", "01_ok")
    assert lib._check(tmp_path) == 0
    make_story(tmp_path, "hi", "01_bad", skip=("timings",))
    assert lib._check(tmp_path) == 1
    out = capsys.readouterr().out
    assert "OK   en/01_ok" in out and "FIX  hi/01_bad: timings.txt is missing" in out


# ── Player ───────────────────────────────────────────────────────────────────

class FakeAudio:
    def __init__(self, length=40.0):
        self.pos, self.len, self.played, self.stopped = 0.0, length, None, False

    def play(self, path):
        self.played = path

    def stop(self):
        self.stopped = True

    def position(self):
        return None if self.pos is None or self.pos >= self.len else self.pos

    def length(self, path):
        return self.len


class FakePrinter:
    def __init__(self):
        self.busy, self.jobs = False, []

    def is_busy(self):
        return self.busy

    def start_print(self, surface):
        self.jobs.append(surface)
        self.busy = True


def _player(tmp_path, **kw):
    story = lib.load_story(make_story(tmp_path, **kw))
    audio, printer = FakeAudio(), FakePrinter()
    loaded = []
    player = StoryPlayer(printer, audio, load_image=lambda p: loaded.append(p.name) or p.name)
    player.start(story)
    return player, audio, printer, story


def test_scene_picture_words_and_print_follow_the_audio(tmp_path):
    player, audio, printer, story = _player(tmp_path)
    assert audio.played == story.audio
    assert player.image == "scene_01.png" and player.sentence == "One."
    assert printer.jobs == ["scene_01.png"]

    audio.pos = 15.0                      # second half of scene 1
    player.update()
    assert player.sentence == "Two." and player.scene_index == 0

    audio.pos = 21.0                      # scene 2 starts; scene 1 still printing
    player.update()
    assert player.image == "scene_02.png" and player.sentence == "Three."
    assert printer.jobs == ["scene_01.png"] and player.prints_waiting() == 2

    printer.busy = False                  # print 1 done -> print 2 starts
    player.update()
    assert printer.jobs == ["scene_01.png", "scene_02.png"]


def test_story_waits_for_prints_then_finishes(tmp_path):
    player, audio, printer, _ = _player(tmp_path, sticker=True)
    audio.pos = 25.0
    player.update()
    audio.pos = None                      # narration over
    player.update()
    assert player.narration_done and not player.is_finished()
    for _ in range(3):                    # scene 1, scene 2, end sticker
        printer.busy = False
        player.update()
    assert printer.jobs == ["scene_01.png", "scene_02.png", "sticker.png"]
    printer.busy = False
    player.update()
    assert player.is_finished() and player.printed == 3


def test_no_scene_print_is_skipped_when_audio_jumps(tmp_path):
    player, audio, printer, _ = _player(
        tmp_path, scenes=(("0:00", "A."), ("0:05", "B."), ("0:10", "C.")))
    audio.pos = 12.0
    player.update()
    printer.busy = False; player.update()
    printer.busy = False; player.update()
    assert printer.jobs == ["scene_01.png", "scene_02.png", "scene_03.png"]


def test_sentence_share_follows_length():
    sentences = ["Short.", "A much much longer sentence here."]
    assert _sentence_at(sentences, 0, 40, 3) == "Short."
    assert _sentence_at(sentences, 0, 40, 10) == sentences[1]
    assert _sentence_at(sentences, 0, None, 30) == "Short."   # unknown length
    assert _sentence_at([], 0, 10, 5) == ""


@pytest.mark.parametrize("mode", ["L", "1", "P", "RGB"])
def test_line_art_in_any_png_mode_can_be_shown_and_printed(tmp_path, mode):
    from PIL import Image
    from services.story_player import load_picture
    from ui.story_screen import StoryScreen
    path = tmp_path / "scene.png"
    Image.new(mode, (300, 200), 0).save(path)
    img = load_picture(path)
    assert img.get_bitsize() >= 24 and img.get_size() == (300, 200)
    player = type("P", (), {"story": type("S", (), {"title": "t"})(), "image": img, "sentence": "Hi.",
                            "narration_done": False})()
    StoryScreen(player).render(pygame.Surface((720, 720)))


def test_story_screen_draws(tmp_path):
    from ui.story_screen import StoryScreen
    story = lib.load_story(make_story(tmp_path, "kn", scenes=(("0:00", "ಆನೆ ಬಂತು. ಇಲಿ ಓಡಿತು."),)))
    player = StoryPlayer(FakePrinter(), FakeAudio())
    player.start(story)
    surface = pygame.Surface((720, 720))
    StoryScreen(player).render(surface)
    player.narration_done = True
    StoryScreen(player).render(surface)
    StoryScreen(None).render(surface)


# ── Story request from the backend ───────────────────────────────────────────

def test_backend_story_answer_skips_the_picture(monkeypatch):
    from services.ai_service import AIService
    from services.backend_client import StickerResult
    monkeypatch.delenv("AI_BACKEND_MODE", raising=False)

    class StoryClient:
        def submit_sticker_stream(self, wav):
            yield "job", {"job_id": "j"}
            yield "text", {"text": "ಕಥೆ ಹೇಳು", "language": "kn"}
            yield "done", {"intent": "story", "language": "kn"}

        def download(self, url):
            raise AssertionError("a story needs no picture")

    ai = AIService(client=StoryClient())
    ai.start_generation("rec.wav")
    ai._thread.join(3)
    assert ai.is_done() and not ai.has_failed()
    assert ai.get_story_language() == "kn" and ai.get_image() is None
    ai.reset()
    assert ai.get_story_language() is None

    assert StickerResult.from_json("j", {"intent": "story"}).intent == "story"
    assert StickerResult.from_json("j", {}).intent == "sticker"


def test_no_story_message():
    from ui.error_screen import ErrorScreen

    class AI:
        def get_error_code(self):
            return "NO_STORY"

    assert ErrorScreen({}, AI()).lines == ("No stories yet.", "Ask me for a picture!")


# ── Button light ─────────────────────────────────────────────────────────────

def test_button_light_follows_the_state():
    from services.button_light import ButtonLight

    class LED:
        def __init__(self):
            self.calls = []

        def on(self):
            self.calls.append("on")

        def off(self):
            self.calls.append("off")

        def pulse(self, **kw):
            self.calls.append("pulse")

    led = LED()
    light = ButtonLight(led)
    for state in (State.IDLE, State.IDLE, State.LISTENING, State.PROCESSING,
                  State.STORY, State.DISPLAYING, State.ERROR):
        light.show(state)
    assert led.calls == ["on", "pulse", "off", "on"]   # repeats are not resent


def test_button_light_without_hardware(monkeypatch):
    from services.button_light import ButtonLight
    monkeypatch.setenv("BUTTON_LED_PIN", "")
    light = ButtonLight()
    light.show(State.IDLE)  # no LED: nothing happens, nothing breaks
    assert light.pattern == "on"
