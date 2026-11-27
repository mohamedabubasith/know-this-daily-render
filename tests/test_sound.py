"""Sound settings an edit can set: the voice start, the quiet between lines, the music. Run: python3 tests/test_sound.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shorts import pipeline as p

SHOT = {"kind": "photo", "anim": {}, "move": "push", "framing": "wide", "transition": "cut", "mood": "calm",
        "overlay": {"kind": "none"}, "ta": "ஒன்று இரண்டு", "en": "one two"}


def film(**kw):
    return {"hook": "Know this", "title": "t", "shots": [dict(SHOT), dict(SHOT)], **kw}


def starts(f):
    return [s["voiceStart"] for s in p.timeline(f, [2.0, 2.0])["shots"]]


assert starts(film()) == [0.3, 2.85]                                  # unchanged: 0.3 s lead, 0.55 s between lines
assert starts(film(format="explainer")) == [0.3, 3.95]                # unchanged: 1.2 s hold + 0.45 s
assert starts(film(sound={"voice_start": 2.5})) == [2.5, 5.05]        # the owner's "start the voice after 2-3 s"
assert starts(film(sound={"gap": 1.0})) == [0.3, 3.3]
t = p.timeline(film(sound={"voice_start": 2.5}), [2.0, 2.0])
assert t["subs"][0]["start"] == 2.5 and t["shots"][0]["start"] == 0.0  # the text waits with the voice; the picture does not
assert p.sound_of(film(sound={"voice_start": 99, "gap": -1, "music": "loud"})) == {"voice_start": 8.0, "gap": 0.15, "music": "on"}
assert p.sound_of(film(format="lesson")) == {"voice_start": 0.5, "gap": 0.35, "music": "on"}
assert p.sound_note(film()) == "" and p.sound_note(film(sound={"voice_start": 2.5, "music": "off"})) == "voice starts at 2.5 s, music off"
print("sound ok")
