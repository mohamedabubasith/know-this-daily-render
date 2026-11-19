"""A lesson's 3D objects, fetched from the models library (the public "models" release of this repo).

  python lesson/models.py K N OUT_DIR      runner K of N fetches its share of film["objects"] into OUT_DIR

The library holds objects Claude built in three.js code (lesson/objects.html, exported by objects.py) and free CC0
models. Nothing here uses a GPU, Hugging Face or any account. An object not in the library is left out; the stage
shows nothing in its place, never a stand-in. FILM_GZ_B64 carries the film (gzip + base64).
"""
import base64
import gzip
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "mohamedabubasith/know-this-daily-render")
LIB = f"https://github.com/{REPO}/releases/download/models/"


def fetch(slug: str, dest: Path) -> bool:
    try:
        with urllib.request.urlopen(f"{LIB}model-{slug}.glb", timeout=60) as r:
            dest.write_bytes(r.read())
        return dest.stat().st_size > 10000
    except Exception:  # noqa: BLE001 - not in the library
        dest.unlink(missing_ok=True)
        return False


if __name__ == "__main__":
    k, n, out = int(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    film = json.loads(gzip.decompress(base64.b64decode(os.environ["FILM_GZ_B64"])))
    for i, o in enumerate(film.get("objects") or []):
        if i % n == k:
            t = time.time()
            ok = fetch(o["slug"], out / f"model-{o['slug']}.glb")
            print(f"{o['slug']}: {'library' if ok else 'not in the library, left out'} ({time.time() - t:.0f}s)", flush=True)
