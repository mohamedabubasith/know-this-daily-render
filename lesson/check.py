"""The scene writer's check: build every scene and step through it, report errors; with times, save stills too.

  python3 check.py            errors only (fast), prints ok when clean
  python3 check.py T [T ...]  also still-T.jpg at each time T (seconds in the whole video)
"""
import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

d = Path(__file__).resolve().parent


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(d)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/stage.html"
dur = json.loads((d / "lesson.json").read_text())["dur"]
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--disable-gpu"])
    pg = b.new_page(viewport={"width": 640, "height": 360})
    pg.on("pageerror", lambda e: errs.append(f"page error: {e}"))
    pg.goto(url + "?warm=1")
    pg.wait_for_function("window.__ready === true", timeout=300000)
    # every scene at many moments, without drawing: only the scene code runs
    errs += pg.evaluate("""(dur) => { const out = [...window.__errors]; for (let t = 0; t < dur; t += 0.25) window.__step(t); return out.concat(window.__errors.slice(out.length)); }""", dur)
    pg.close()
    if sys.argv[1:]:  # stills: one page, half size, a short warm-up (enough to judge layout)
        pg = b.new_page(viewport={"width": 960, "height": 540}, device_scale_factor=1)
        pg.on("pageerror", lambda e: errs.append(f"page error: {e}"))
        pg.goto(f"{url}?warm=3&small=1")
        pg.wait_for_function("window.__ready === true", timeout=300000)
        pg.evaluate("document.fonts.ready")
        for t in sys.argv[1:]:
            for k in (3, 2, 1, 0):
                pg.evaluate(f"renderAt({max(0.0, float(t) - k / 30)})")
            pg.screenshot(path=str(d / f"still-{t}.jpg"), type="jpeg", quality=80)
            print(f"saved still-{t}.jpg", flush=True)
        pg.close()
    b.close()
errs = list(dict.fromkeys(errs))
for e in errs[:30]:
    print("ERROR", e[:400])
print("ok" if not errs else f"{len(errs)} errors")
sys.exit(1 if errs else 0)
