"""The hand-built 3D objects (objects.html, three.js code) exported as GLB files:  python3 objects.py OUT_DIR

Each lands as OUT_DIR/model-<name>.glb, the same form as the models library (release "models"), so K.model finds it."""
import base64
import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--disable-gpu"])
    page = b.new_page()
    page.on("console", lambda m: m.type == "error" and print("ERROR", m.text))
    page.on("pageerror", lambda e: sys.exit(f"objects.html: {e}"))
    page.goto(f"http://127.0.0.1:{srv.server_port}/objects.html")
    page.wait_for_function("window.DONE === true", timeout=120000)
    for name, b64 in page.evaluate("window.GLB").items():
        (out / f"model-{name}.glb").write_bytes(base64.b64decode(b64))
        print(f"model-{name}.glb {len(b64) * 3 // 4 // 1024} KB")
    b.close()
srv.shutdown()
