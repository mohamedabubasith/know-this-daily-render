"""Assemble an authored explainer into a HyperFrames project. Run in the project folder: python3 build.py

Reads   timing.json   the film's clock (written by the pipeline, never by the author)
        scenes.json   [{"id": "kitchen", "shots": [0, 1], "bg": "#E8683A"}, ...] in film order (written by the author)
        scenes/<id>.html   one scene per file (written by the author)
        lib.js        shared helpers, inlined where a scene says /*LIB*/
Writes  compositions/*.html (scenes, captions, brand, endcard) and index.html.

In a scene, /*T*/ becomes that scene's own clock (seconds from the scene's start):
  { D: scene length, shots: [{ i, v0, v1, end, en }] }  v0/v1 = the voice line's start/end, end = when the shot ends.
Errors are printed as "ERROR: ..." and the exit code is 1.
"""
import html
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent
T = json.loads((HERE / "timing.json").read_text())
SHOTS, DUR, END = T["shots"], T["duration"], T["endStart"]
INK, DOT, CREAM = "#1F1235", "#FFD23F", "#FFF4DC"
TAMIL = any("\u0b80" <= ch <= "\u0bff" for c in T["subs"] for ch in c["text"])  # Tamil subtitles: smaller, taller lines
FONT_FACE = '@font-face { font-family: "Noto Sans Tamil"; src: url("assets/fonts/NotoSansTamil.ttf"); font-weight: 100 900; }'
errors = []


def r(x: float) -> float:
    return round(x, 3)


try:
    scenes = json.loads((HERE / "scenes.json").read_text())
except (OSError, ValueError) as e:
    sys.exit(f"ERROR: scenes.json is missing or not JSON: {e}")
covered = [i for s in scenes for i in s.get("shots", [])]
if covered != list(range(len(SHOTS))):
    errors.append(f"scenes.json must cover shots 0..{len(SHOTS) - 1} once each, in order; it covers {covered}")
ids = [s.get("id", "") for s in scenes]
if len(set(ids)) != len(ids) or not all(re.fullmatch(r"[a-z][a-z0-9]{1,11}", i) for i in ids):
    errors.append("scene ids must be unique, lowercase letters/digits, 2 to 12 characters")
if errors:
    sys.exit("\n".join("ERROR: " + e for e in errors))

lib = (HERE / "lib.js").read_text()
out = HERE / "compositions"
out.mkdir(exist_ok=True)
for old in out.glob("*.html"):
    old.unlink()
hosts = []
for n, s in enumerate(scenes):
    first, last = SHOTS[s["shots"][0]], SHOTS[s["shots"][-1]]
    start = 0.0 if n == 0 else first["start"]
    end = DUR if n == len(scenes) - 1 else SHOTS[s["shots"][-1] + 1]["start"]
    clock = {"D": r(end - start), "shots": [{"i": i, "v0": r(SHOTS[i]["voiceStart"] - start), "v1": r(SHOTS[i]["voiceEnd"] - start),
                                             "end": r(min(SHOTS[i]["end"], end) - start), "en": SHOTS[i]["en"].replace("*", "")} for i in s["shots"]]}
    f = HERE / "scenes" / f"{s['id']}.html"
    if not f.exists():
        errors.append(f"scenes/{s['id']}.html is missing")
        continue
    src = f.read_text()
    for must, why in (("<template>", "a scene file is wrapped in <template>"), ("/*LIB*/", "put /*LIB*/ first in the scene's script"),
                      ("/*T*/", "read the clock with: const T = /*T*/;"), (f'data-composition-id="{s["id"]}"', "the scene root needs this id"),
                      (f'window.__timelines["{s["id"]}"]', "register the timeline under the scene id")):
        if must not in src:
            errors.append(f"scenes/{s['id']}.html: {why} (missing {must})")
    for bad, why in ((r"repeat:\s*-1", "no repeat: -1 (use amb(), a finite loop)"), (r"Math\.random|Date\.now|setTimeout|setInterval|requestAnimationFrame", "no clocks, timers or Math.random (use rng(seed))"),
                     (r"[\U0001F300-\U0001FAFF☀-➿]", "no emoji: draw it"), (r"onUpdate", "no onUpdate: tween attributes and transforms directly")):
        if re.search(bad, src):
            errors.append(f"scenes/{s['id']}.html: {why}")
    if re.search(r"noto sans tamil", src, re.I) and "@font-face" not in src:
        src = src.replace("<style>", "<style>\n    " + FONT_FACE, 1)
    (out / f.name).write_text(src.replace("/*LIB*/", lib).replace("/*T*/", json.dumps(clock, ensure_ascii=False)))
    hosts.append(f'      <div id="{s["id"]}" data-composition-id="{s["id"]}" data-composition-src="compositions/{s["id"]}.html" data-start="{r(start)}" '
                 f'data-duration="{r(end - start)}" data-track-index="1" data-track-kind="graphics" data-width="1080" data-height="1920" style="z-index:1"></div>')
if errors:
    sys.exit("\n".join("ERROR: " + e for e in errors))

# ---- captions: one clip per subtitle chunk; *word* is the highlighted key word
groups, js = [], []
for i, c in enumerate(T["subs"]):
    txt = re.sub(r"\*(.+?)\*([.,!?]*)", r'<span style="white-space:nowrap"><span class="cap-hl" id="cap-%d-hl">\1</span>\2</span>' % i, html.escape(c["text"]))
    groups.append(f'    <div id="cap-{i}" class="clip cap" data-start="{c["start"]}" data-duration="{r(c["end"] - c["start"])}" data-track-index="1"><div class="cap-in" id="cap-{i}-in">{txt}</div></div>')
    js.append(f'[{i},{c["start"]},{c["end"]},{1 if "*" in c["text"] else 0}]')
(out / "captions.html").write_text(f"""<template>
  <style>
    {FONT_FACE if TAMIL else ""}
    #root {{ position: absolute; inset: 0; }}
    .cap {{ position: absolute; left: 60px; width: 960px; top: 1146px; height: 170px; display: flex; align-items: flex-end; justify-content: center; overflow: visible; }}
    .cap-in {{ font-family: {'"Noto Sans Tamil", ' if TAMIL else ""}"Nunito", sans-serif; font-weight: 900; font-size: {58 if TAMIL else 68}px; line-height: {1.3 if TAMIL else 1.1}; color: #fff; text-align: center; text-wrap: balance;
      -webkit-text-stroke: 16px {INK}; paint-order: stroke fill; text-shadow: 0 7px 0 {INK}; }}
    .cap-hl {{ display: inline-block; color: {DOT}; }}
  </style>
  <div id="root" data-composition-id="captions" data-width="1080" data-height="1920">
{chr(10).join(groups)}
  </div>
  <script>
    (function () {{
      const tl = gsap.timeline({{ paused: true }});
      [{",".join(js)}].forEach(function (c) {{
        const el = "#cap-" + c[0] + "-in";
        tl.fromTo(el, {{ opacity: 0, y: 20, scale: 0.94 }}, {{ opacity: 1, y: 0, scale: 1, duration: 0.14, ease: "power3.out" }}, c[1]);
        if (c[3]) tl.fromTo("#cap-" + c[0] + "-hl", {{ scale: 1.18 }}, {{ scale: 1, duration: 0.35, ease: "back.out(2.5)" }}, c[1] + 0.06);
        tl.to(el, {{ opacity: 0, duration: 0.08, ease: "power2.in" }}, c[2] - 0.09);
      }});
      window.__timelines["captions"] = tl;
    }})();
  </script>
</template>
""")

# ---- brand mark (top left, until the end card) and the end card
(out / "brand.html").write_text(f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; }}
    #brand-mark {{ position: absolute; left: 48px; top: 182px; width: 420px; height: 64px; }}
    #brand-in {{ position: absolute; left: 0; top: 0; height: 64px; padding: 0 26px 0 14px; border-radius: 32px; background: {INK}; display: flex; align-items: center; gap: 12px;
      font-family: "Nunito", sans-serif; font-weight: 900; font-size: 30px; letter-spacing: 0.06em; color: {CREAM}; white-space: nowrap; }}
    #brand-sun {{ width: 38px; height: 38px; border-radius: 50%; background: {DOT}; }}
  </style>
  <div id="root" data-composition-id="brand" data-width="1080" data-height="1920">
    <div id="brand-mark" class="clip" data-start="0.6" data-duration="{r(END - 0.6)}" data-track-index="1">
      <div id="brand-in"><div id="brand-sun"></div><span>KNOW THIS DAILY</span></div>
    </div>
  </div>
  <script>
    (function () {{
      const tl = gsap.timeline({{ paused: true }});
      tl.fromTo("#brand-in", {{ opacity: 0, x: -40 }}, {{ opacity: 1, x: 0, duration: 0.4, ease: "power4.out" }}, 0.6);
      tl.to("#brand-in", {{ opacity: 0, x: -30, duration: 0.2, ease: "power2.in" }}, {r(END - 0.25)});
      window.__timelines["brand"] = tl;
    }})();
  </script>
</template>
""")
rays = "".join(f'<path d="M 0 0 L {900 * __import__("math").cos(a - 0.1):.0f} {900 * __import__("math").sin(a - 0.1):.0f} L {900 * __import__("math").cos(a + 0.1):.0f} {900 * __import__("math").sin(a + 0.1):.0f} Z"/>'
               for a in [i * 3.14159 / 8 for i in range(16)])
(out / "endcard.html").write_text(f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; overflow: hidden; }}
    #end-in {{ position: absolute; inset: 0; background: {DOT}; }}
    #end-svg {{ position: absolute; left: 0; top: 0; }}
    #end-name {{ position: absolute; left: 0; width: 1080px; top: 610px; text-align: center; font-family: "Nunito", sans-serif; font-weight: 900; font-size: 128px; line-height: 0.98; color: {INK}; }}
    #end-name span {{ display: block; color: #E8336D; font-size: 168px; }}
    #end-line {{ position: absolute; left: 140px; width: 800px; top: 960px; text-align: center; font-family: "Nunito", sans-serif; font-weight: 900; font-size: 54px; line-height: 1.15; color: {INK}; }}
  </style>
  <div id="root" data-composition-id="endcard" data-width="1080" data-height="1920">
    <div id="end-card" class="clip" data-start="0" data-duration="{r(DUR - END)}" data-track-index="1">
      <div id="end-in">
        <svg id="end-svg" width="1080" height="1920" viewBox="0 0 1080 1920" data-layout-ignore><g id="end-rays" transform="translate(540 760)" fill="#FFE27A">{rays}</g></svg>
        <div id="end-name">KNOW THIS<span>DAILY</span></div>
        <div id="end-line">Follow for one new thing every day</div>
      </div>
    </div>
  </div>
  <script>
    (function () {{
      const tl = gsap.timeline({{ paused: true }});
      tl.fromTo("#end-in", {{ clipPath: "circle(0% at 50% 40%)" }}, {{ clipPath: "circle(120% at 50% 40%)", duration: 0.55, ease: "power3.out" }}, 0);
      tl.fromTo("#end-rays", {{ rotation: 0, svgOrigin: "0 0" }}, {{ rotation: 40, duration: {r(DUR - END)}, ease: "none" }}, 0);
      tl.fromTo("#end-name", {{ opacity: 0, scale: 0.6 }}, {{ opacity: 1, scale: 1, duration: 0.5, ease: "back.out(1.8)" }}, 0.25);
      tl.fromTo("#end-line", {{ opacity: 0, y: 40 }}, {{ opacity: 1, y: 0, duration: 0.4, ease: "power3.out" }}, 0.6);
      window.__timelines["endcard"] = tl;
    }})();
  </script>
</template>
""")


def host(cid: str, start: float, dur: float, track: int, kind: str, z: int) -> str:
    return (f'      <div id="{cid}" data-composition-id="{cid}" data-composition-src="compositions/{cid}.html" data-start="{r(start)}" data-duration="{r(dur)}" '
            f'data-track-index="{track}" data-track-kind="{kind}" data-width="1080" data-height="1920" style="z-index:{z}"></div>')


bg = scenes[0].get("bg", INK)
(HERE / "index.html").write_text(f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: 1080px; height: 1920px; overflow: hidden; background: {bg}; }}
      #root {{ position: relative; width: 1080px; height: 1920px; overflow: hidden; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{DUR}" data-width="1080" data-height="1920">
{chr(10).join(hosts)}
{host("brand", 0, DUR, 2, "graphics", 5)}
{host("captions", 0, DUR, 3, "captions", 6)}
{host("endcard", END, DUR - END, 4, "graphics", 7)}
      <audio id="voice" class="clip" src="assets/voice.mp3" data-start="0" data-duration="{DUR}" data-track-index="0" data-volume="1"></audio>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
""")
print(f"built {len(scenes)} scenes, {len(T['subs'])} captions, {DUR} s")
