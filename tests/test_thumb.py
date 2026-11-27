"""The thumbnail: its words, the picture it falls back to, and the page it is drawn from. Run: python3 tests/test_thumb.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shorts import pipeline as p
from shorts import thumb

shot = {"ta": "x", "en": "y", "kind": "photo", "image": "i"}
film = {"hook": "Thousands of Buried Pots", "title": "a | b", "hashtags": [], "shots": [dict(shot) for _ in range(3)]}
assert p.clean_film(dict(film))["thumb"] == {"words": "Thousands of Buried Pots", "line": "", "shot": 0}  # an older film: the hook
assert p.clean_film({**film, "thumb": {"words": "a b c d e f", "line": "", "shot": 99}})["thumb"] == {"words": "a b c d e", "line": "", "shot": 2}
assert thumb.marked("Regions *&* <Zones>") == "Regions <b>&amp;</b> &lt;Zones&gt;"

with tempfile.TemporaryDirectory() as d:
    job = Path(d)
    (job / "project" / "assets").mkdir(parents=True)
    (job / "project" / "assets" / "shot-0.jpg").write_bytes(b"x")
    text, size = thumb.page({**film, "thumb": {"words": "மண் தாழிகள் *ரகசியம்*", "line": "", "shot": 2}}, job)
    assert size == (1080, 1920) and "shot-0.jpg" in text and 'class="ta"' in text and "<b>ரகசியம்</b>" in text  # shot 2 has no picture: the first one
print("thumb ok")
