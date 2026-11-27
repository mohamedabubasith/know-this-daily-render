"""The thumbnail of a finished video, drawn as a web page and photographed with Chrome.

  python -m shorts.thumb JOB_DIR    JOB_DIR holds film.json, project/ and video.mp4; writes JOB_DIR/thumb.jpg

A 16:9 lesson gets a 1280x720 thumbnail: a navy panel with the words, the host beside it.
A Short gets a 1080x1920 cover: its most striking picture with the words over it.
The words come from film.thumb (written by the script writer); the hook stands in for an older film.
"""
import html
import json
import re
import subprocess
import sys
from pathlib import Path

FONT_TA = Path(__file__).parent / "template" / "assets" / "fonts" / "NotoSansTamil.ttf"
FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Catamaran:wght@800;900'
         '&family=Inter:wght@600;700;800&display=swap" rel="stylesheet">')
TAMIL = re.compile(r"[஀-௿]")

WIDE = """<!doctype html><meta charset="utf-8">{fonts}
<style>
@font-face {{ font-family: "Noto Sans Tamil"; src: url("{font_ta}"); font-weight: 100 900; }}
html,body{{margin:0}}
#r{{position:relative;width:1280px;height:720px;overflow:hidden;background:#ebebea;font-family:Inter,"Noto Sans Tamil",sans-serif}}
#pic{{position:absolute;right:-10px;top:-6px;height:732px}}
#edge{{position:absolute;left:0;top:0;width:776px;height:720px;background:#ffc21a;clip-path:polygon(0 0,100% 0,82% 100%,0 100%)}}
#panel{{position:absolute;left:0;top:0;width:760px;height:720px;background:#141b4d;clip-path:polygon(0 0,100% 0,82% 100%,0 100%)}}
#brand{{position:absolute;left:70px;top:58px;font:800 26px/1 Inter;letter-spacing:.14em;color:#fff;opacity:.85}}
#txt{{position:absolute;left:70px;top:150px;width:590px;color:#fff}}
.part{{font:900 30px/1.1 Inter,"Noto Sans Tamil";letter-spacing:.14em;color:#ffc21a;text-transform:uppercase}}
h1{{margin:26px 0 0;font:900 132px/0.94 Catamaran,"Noto Sans Tamil",sans-serif;letter-spacing:-.01em;text-transform:uppercase;overflow-wrap:break-word}}
h1.ta{{line-height:1.22;letter-spacing:0}}
h1 b{{color:#ffc21a}}
.sub{{margin-top:26px;font:700 36px/1.2 Inter,"Noto Sans Tamil";color:#cfd4f2;max-width:520px}}
</style>
<div id="r"><img id="pic" src="{pic}"><div id="edge"></div><div id="panel"></div><div id="brand">KNOW THIS DAILY</div>
<div id="txt"><div class="part">{label}</div><h1 id="h" class="{cls}">{words}</h1><div class="sub">{line}</div></div></div>
<script>window.fit = () => {{ const h = document.getElementById("h"); let s = 132;
  while (s > 56 && (h.scrollWidth > 590 || h.offsetHeight > {max_h})) h.style.fontSize = (s -= 4) + "px"; }};</script>
"""

TALL = """<!doctype html><meta charset="utf-8">{fonts}
<style>
@font-face {{ font-family: "Noto Sans Tamil"; src: url("{font_ta}"); font-weight: 100 900; }}
html,body{{margin:0}}
#r{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#0b0d1c}}
#pic{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
#g{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(8,9,20,.55) 0%,rgba(8,9,20,0) 22%,rgba(8,9,20,0) 40%,rgba(8,9,20,.88) 70%,rgba(8,9,20,.94) 100%)}}
#bug{{position:absolute;left:0;right:0;top:120px;text-align:center;font:700 34px/1 Inter;letter-spacing:.2em;color:#fff}}
#bar{{position:absolute;left:50%;top:964px;width:150px;height:12px;margin-left:-75px;background:#ffd21f;border-radius:6px}}
h1{{position:absolute;left:70px;right:70px;top:1020px;margin:0;text-align:center;color:#fff;text-wrap:balance;overflow-wrap:break-word;
  text-shadow:0 6px 30px rgba(0,0,0,.6);font:400 112px/1.06 "Archivo Black","Noto Sans Tamil",sans-serif;text-transform:uppercase}}
h1.ta{{font:900 112px/1.28 "Noto Sans Tamil",sans-serif}}
h1 b{{color:#ffd21f;font-weight:inherit}}
</style>
<div id="r"><img id="pic" src="{pic}"><div id="g"></div><div id="bug">KNOW THIS DAILY</div><div id="bar"></div>
<h1 id="h" class="{cls}">{words}</h1></div>
<script>window.fit = () => {{ const h = document.getElementById("h"); let s = 112;
  while (s > 56 && (h.scrollWidth > 940 || h.offsetHeight > 420)) h.style.fontSize = (s -= 4) + "px"; }};</script>
"""


def marked(words: str) -> str:
    """Safe HTML of the words; *word* becomes the highlighted word."""
    return re.sub(r"\*([^*]+)\*", r"<b>\1</b>", html.escape(words)).replace("*", "")


def frame(video: Path, t: float, dest: Path, crop: str = "") -> Path:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0.0, t):.2f}", "-i", str(video), "-frames:v", "1",
                    *(["-vf", crop] if crop else []), "-q:v", "2", str(dest)], check=True, timeout=120)
    return dest


def timing(project: Path) -> list[dict]:
    """Each line's voice times: timing.json (drawn films, lessons) or assets/film.js (picture films)."""
    try:
        if (project / "timing.json").exists():
            d = json.loads((project / "timing.json").read_text())
        else:
            js = (project / "assets" / "film.js").read_text()
            d = json.loads(js[js.index("{"):js.rindex("}") + 1])
        return [s for s in d.get("shots", []) if "voiceStart" in s]
    except (OSError, ValueError):
        return []


def page(film: dict, job: Path) -> tuple[str, tuple[int, int]]:
    """The thumbnail as a web page, and its size."""
    work = job / "work"
    work.mkdir(parents=True, exist_ok=True)
    project, video = job / "project", job / "video.mp4"
    t = film.get("thumb") or {}
    words = str(t.get("words") or film.get("hook") or film.get("en_title") or "Know this")
    shots = timing(project)
    common = {"fonts": FONTS, "font_ta": FONT_TA.as_uri(), "words": marked(words), "cls": "ta" if TAMIL.search(words) else ""}
    if film.get("format") == "lesson":
        # The host, alone, from the intro: she stands in the middle there and nothing overlaps her.
        # ponytail: one fixed moment; a blink in that frame is possible. Pick among a few frames if it ever shows.
        at = (shots[1]["voiceStart"] + 0.8) if len(shots) > 1 else 2.0
        pic = frame(video, at, work / "thumb-pic.jpg", "crop=iw*0.38:ih*0.9:iw*0.31:ih*0.1")
        series = str(film.get("series") or "").strip()
        label = f"{series} · {int(film.get('part') or 1):02d}" if series else ""
        line = str(t.get("line") or "")
        return WIDE.format(**common, pic=pic.as_uri(), label=html.escape(label), line=html.escape(line),
                           max_h=330 if line else 400), (1280, 720)
    i = min(max(int(t.get("shot") or 0), 0), max(0, len(film.get("shots", [])) - 1))
    pics = sorted((project / "assets").glob("shot-*.jpg"))
    pic = project / "assets" / f"shot-{i}.jpg"
    if not pic.exists():  # an animated-graphic shot or a drawn film has no picture of its own
        if film.get("format") == "explainer" or not pics:  # the finished drawing of that shot, from the film itself
            pic = frame(video, shots[i]["voiceEnd"] + 0.3 if i < len(shots) else 1.0, work / "thumb-pic.jpg")
        else:
            pic = pics[0]
    return TALL.format(**common, pic=pic.as_uri()), (1080, 1920)


def make(job: Path) -> Path:
    from playwright.sync_api import sync_playwright

    film = json.loads((job / "film.json").read_text())
    text, (w, h) = page(film, job)
    src = job / "work" / "thumb.html"
    src.write_text(text)
    out = job / "thumb.jpg"
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True, args=["--allow-file-access-from-files"])
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.goto(src.as_uri(), wait_until="load", timeout=60000)
        pg.evaluate("document.fonts.ready.then(() => window.fit())")
        pg.screenshot(path=str(out), type="jpeg", quality=88)  # far under YouTube's 2 MB limit
        b.close()
    return out


if __name__ == "__main__":
    print(make(Path(sys.argv[1]).resolve()))
