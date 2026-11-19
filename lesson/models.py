"""Real 3D models for a lesson's objects: the owner's rule is that every real thing on screen is a real 3D model.

  python lesson/models.py K N OUT_DIR      runner K of N makes or fetches its share of film["objects"] into OUT_DIR

Each object ({"slug", "name", "look"}) comes from the library first: the public "models" release of this repo, where
every model made so far is kept (a broom is made once and reused). A new one is made on Hugging Face's free GPUs:
an accurate picture of the object alone (Z-Image Turbo, Apache-2.0), then the picture turned into a textured 3D
model (TRELLIS.2, MIT), exported as GLB, and added to the library. A model that cannot be made is left out; the
stage shows nothing in its place, never a stand-in.
FILM_GZ_B64 carries the film (gzip + base64); HF_TOKEN (optional) is the fallback when the guest GPU quota is spent.
"""
import base64
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "mohamedabubasith/know-this-daily-render")
TAG = "models"
LIB = f"https://github.com/{REPO}/releases/download/{TAG}/"


def picture(obj: dict, dest: Path, token: str | None) -> None:
    from gradio_client import Client
    prompt = (f"{obj['look']}. One single {obj['name']}, the whole object fully visible with space around it, upright in "
              "its normal position as people see and use it, isolated on a plain pure white background, centred, product "
              "photo, soft even studio light, photoreal, true to life, sharp focus, no text, no logo")
    c = Client("Tongyi-MAI/Z-Image-Turbo", token=token, verbose=False)
    res = c.predict(prompt=prompt, resolution="1024x1024 ( 1:1 )", seed=7, random_seed=False, api_name="/generate")
    img = res[0] if isinstance(res, (list, tuple)) else res
    while isinstance(img, list):
        img = img[0]
    if isinstance(img, dict):
        img = img.get("image") or img.get("path") or img
    if isinstance(img, dict):
        img = img.get("path")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", img, str(dest)], check=True)


def to_3d(image: Path, dest: Path, token: str | None) -> None:
    from gradio_client import Client, handle_file
    c = Client("microsoft/TRELLIS.2", token=token, verbose=False)
    c.predict(api_name="/start_session")
    pre = c.predict(handle_file(str(image)), api_name="/preprocess_image")
    c.predict(handle_file(pre if isinstance(pre, str) else pre["path"]), 7, "1024", api_name="/image_to_3d")
    glb, dl = c.predict(100000, 1024, api_name="/extract_glb")  # 100k faces, 1024 px texture: a few MB, sharp enough
    shutil.copy(dl or glb, dest)
    if not dest.exists() or dest.stat().st_size < 10000:
        raise RuntimeError("TRELLIS gave no model")


def fetch(slug: str, dest: Path) -> bool:
    try:
        with urllib.request.urlopen(f"{LIB}model-{slug}.glb", timeout=60) as r:
            dest.write_bytes(r.read())
        return dest.stat().st_size > 10000
    except Exception:
        return False


def make(obj: dict, out: Path) -> str:
    dest = out / f"model-{obj['slug']}.glb"
    if fetch(obj["slug"], dest):
        return "library"
    token = os.environ.get("HF_TOKEN") or None
    last = ""
    for who in [None] + ([token] if token else []):  # the guest quota first (each runner has its own), then the account's
        try:
            with tempfile.TemporaryDirectory() as tmp:
                img = Path(tmp) / "object.png"
                picture(obj, img, who)
                to_3d(img, dest, who)
            break
        except Exception as e:  # noqa: BLE001 - quota or a busy GPU: try the other quota, then give up on this object
            last = str(e)[:300]
            print(f"  {obj['slug']}: {'guest' if who is None else 'account'} failed: {last}", flush=True)
            time.sleep(5)
    else:
        return "missing: " + last
    if not dest.exists():
        return "missing: " + last
    if os.environ.get("GH_TOKEN"):  # keep it in the library for every later video
        up = subprocess.run(["gh", "release", "upload", TAG, str(dest), "-R", REPO, "--clobber"], capture_output=True, text=True)
        if up.returncode:
            print(f"  {obj['slug']}: not added to the library: {up.stderr[-200:]}", flush=True)
    return "made"


if __name__ == "__main__":
    k, n, out = int(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    film = json.loads(gzip.decompress(base64.b64decode(os.environ["FILM_GZ_B64"])))
    objs = [o for i, o in enumerate(film.get("objects") or []) if i % n == k]
    for o in objs:
        t = time.time()
        print(f"{o['slug']}: {make(o, out)} ({time.time() - t:.0f}s)", flush=True)
    made = sorted(p.name[6:-4] for p in out.glob("model-*.glb"))
    print("models here:", made)
