"""Frames of the lesson stage (stage.html, three.js) with Chrome on CPU.

  python capture.py DIR still T [T ...]   DIR/still-T.jpg for each time T, and any scene errors (for the writer's checks)
  python capture.py DIR chunk A B OUT     frames A..B-1 (30 fps) -> OUT.mp4, no sound

DIR holds stage.html, stations.js, lesson.json, env.json, host.vrm and dress.png. Every frame depends only on its time,
except hair physics and mouth smoothing, which a 3-second warm-up before the first frame settles.
"""
import functools
import http.server
import subprocess
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

FPS = 30
d = Path(sys.argv[1]).resolve()
mode = sys.argv[2]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(d)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/stage.html"
ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--disable-gpu"]


def open_page(b, t0: float):
    pg = b.new_page(viewport={"width": 1920, "height": 1080})
    errs = []
    pg.on("pageerror", lambda e: errs.append(f"page error: {e}"))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(f"{url}?t={t0:.3f}")
    pg.wait_for_function("window.__ready === true", timeout=300000)
    pg.evaluate("document.fonts.ready")
    return pg, errs


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=ARGS)
    if mode == "still":
        bad = []
        for t in sys.argv[3:]:
            pg, errs = open_page(b, float(t))
            pg.evaluate(f"renderAt({float(t)})")
            pg.screenshot(path=str(d / f"still-{t}.jpg"), type="jpeg", quality=85)
            bad += errs
            pg.close()
        for e in dict.fromkeys(bad):
            print("ERROR", e[:300])
        print("stills:", ", ".join(f"still-{t}.jpg" for t in sys.argv[3:]))
    elif mode == "chunk":
        a, z, out = int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
        pg, errs = open_page(b, a / FPS)
        enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
                                "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS), out], stdin=subprocess.PIPE)
        for i in range(a, z):
            pg.evaluate(f"renderAt({i / FPS})")
            enc.stdin.write(pg.screenshot(type="jpeg", quality=92))
            if (i - a) % 150 == 0:
                print(f"frame {i} ({i - a + 1}/{z - a})", flush=True)
        enc.stdin.close()
        if enc.wait():
            sys.exit("ffmpeg failed")
        for e in dict.fromkeys(errs):
            print("ERROR", e[:300])
    b.close()
