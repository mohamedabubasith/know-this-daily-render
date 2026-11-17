"""Make one Know This Daily video from a shot list, on a GitHub Actions runner.

Usage: python render.py JOB_DIR   (JOB_DIR holds film.json; video.mp4, preview.mp4 and facts.json are written there)
The film.json can also come gzip+base64 in the FILM_GZ_B64 environment variable (the workflow input).
"""
import base64
import gzip
import json
import os
import sys
import traceback
from pathlib import Path

from shorts import pipeline as p

job = Path(sys.argv[1]).resolve()
(job / "work").mkdir(parents=True, exist_ok=True)
if os.environ.get("FILM_GZ_B64"):
    (job / "film.json").write_bytes(gzip.decompress(base64.b64decode(os.environ["FILM_GZ_B64"])))
film = json.loads((job / "film.json").read_text())
print(f"film: {film.get('title', '?')} | {film.get('format')} | {len(film['shots'])} shots", flush=True)

try:
    facts = p.make_video(film, job, lambda step: print(f"step: {step}", flush=True))
    facts.pop("usage", None)
    facts["ok"] = True
except Exception as e:  # noqa: BLE001 - the brain reads facts.json to tell the owner what went wrong
    traceback.print_exc()
    facts = {"ok": False, "error": (str(e) if isinstance(e, p.StepError) else f"{type(e).__name__}: {e}")[:1500]}
(job / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1))
print(json.dumps(facts, ensure_ascii=False), flush=True)
sys.exit(0 if facts["ok"] else 1)
