"""Play a pre-recorded story: audio, a picture and words per scene, and a
printed sticker of each scene's picture.

The whole story is one audio file. update() (called every frame) reads how
far the audio has played and, when a scene's start time from timings.txt is
reached, switches the picture and words and queues that picture for printing.
Prints go one at a time in order; if a scene is shorter than a print (about
18 s at 9600 baud), the prints finish a little after the story.
"""

import pygame

from services.story_library import Story


def load_picture(path) -> pygame.Surface:
    """Load a scene picture as a full-colour surface.

    Black-and-white line art is often saved as a grayscale or 1-bit PNG;
    pygame cannot smooth-scale those, so they are copied to 24-bit first.
    """
    img = pygame.image.load(str(path))
    if img.get_bitsize() < 24:
        rgb = pygame.Surface(img.get_size())
        rgb.fill((255, 255, 255))
        rgb.blit(img, (0, 0))
        img = rgb
    return img


class MixerAudio:
    """pygame.mixer.music, wrapped so tests can swap it out."""

    def __init__(self):
        if not pygame.mixer.get_init():
            pygame.mixer.init()

    def play(self, path):
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()

    def stop(self):
        pygame.mixer.music.stop()

    def position(self):
        """Seconds played, or None once it has stopped."""
        ms = pygame.mixer.music.get_pos()
        return None if ms < 0 or not pygame.mixer.music.get_busy() else ms / 1000.0

    def length(self, path):
        try:
            return pygame.mixer.Sound(str(path)).get_length()
        except Exception:
            return None


def _sentence_at(sentences, start, end, pos):
    """The sentence to show at `pos`: each gets a share of the scene's time
    that matches its length, so the words roughly follow the voice."""
    if not sentences:
        return ""
    if end is None or end <= start:
        return sentences[0]
    weights = [max(1, len(s)) for s in sentences]
    span, total, t = end - start, sum(weights), start
    for sentence, w in zip(sentences, weights):
        t += span * w / total
        if pos < t:
            return sentence
    return sentences[-1]


class StoryPlayer:
    def __init__(self, printer=None, audio=None, load_image=None):
        self.printer = printer
        self.audio = audio or MixerAudio()
        self._load_image = load_image or load_picture
        self.story = None
        self._reset()

    def _reset(self):
        self.scene_index = -1
        self.image = None
        self._shown = None
        self.sentence = ""
        self.position = 0.0
        self.narration_done = False
        self._length = None
        self._queue = []
        self._sticker_queued = False
        self.printed = 0

    # ------------------------
    # Control
    # ------------------------
    def start(self, story: Story):
        self.stop()
        self._reset()
        self.story = story
        self._length = self.audio.length(story.audio)
        print(f"[STORY] start {story.name} '{story.title_en}' "
              f"({len(story.scenes)} scenes, {self._length or '?'} s)", flush=True)
        self.audio.play(story.audio)
        self.update()

    def stop(self):
        if self.story is not None and not self.narration_done:
            self.audio.stop()
        self._queue.clear()
        self.story = None

    # ------------------------
    # Every frame
    # ------------------------
    def update(self):
        if self.story is None:
            return
        if not self.narration_done:
            pos = self.audio.position()
            if pos is None:
                self.narration_done = True
                print("[STORY] narration finished", flush=True)
            else:
                self.position = pos
                self._follow(pos)
        if self.narration_done and not self._sticker_queued:
            self._sticker_queued = True
            if self.story.sticker is not None:
                self._queue.append(self.story.sticker)
        self._feed_printer()

    def _follow(self, pos):
        scenes = self.story.scenes
        index = max((i for i, s in enumerate(scenes) if s.start <= pos), default=0)
        while self.scene_index < index:  # never skip a scene's print
            self.scene_index += 1
            scene = scenes[self.scene_index]
            self._queue.append(scene.image)
            print(f"[STORY] scene {scene.number} at {pos:.1f} s", flush=True)
        scene = scenes[self.scene_index]
        if self._shown != scene.image:
            try:
                self.image = self._load_image(scene.image)
            except Exception as e:
                print(f"[STORY] cannot show {scene.image}: {e}", flush=True)
                self.image = None
            self._shown = scene.image
        nxt = scenes[self.scene_index + 1].start if self.scene_index + 1 < len(scenes) else self._length
        self.sentence = _sentence_at(scene.sentences, scene.start, nxt, pos)

    def _feed_printer(self):
        if not self._queue or self.printer is None or self.printer.is_busy():
            return
        path = self._queue.pop(0)
        try:
            self.printer.start_print(self._load_image(path))
            self.printed += 1
        except Exception as e:
            print(f"[STORY] cannot print {path}: {e}", flush=True)

    # ------------------------
    # Status
    # ------------------------
    def prints_waiting(self) -> int:
        busy = 1 if self.printer is not None and self.printer.is_busy() else 0
        return len(self._queue) + busy

    def is_finished(self) -> bool:
        return self.story is not None and self.narration_done and self.prints_waiting() == 0
