"""One part of a video, made on its own GitHub Actions runner so the parts run at the same time.

  python part.py voice K N JOB_DIR   voice lines K, K+N, K+2N, ... (voice G, IndicF5 on this runner)
  python part.py pictures JOB_DIR    every picture

Results land in ./cache (voice/, pictures/), keyed by their text or prompt, where render.py finds them.
The film.json comes in FILM_GZ_B64 (gzip + base64), as for render.py.
"""
import base64
import gzip
import json
import os
import sys
from pathlib import Path

from shorts import pipeline as p

kind, job = sys.argv[1], Path(sys.argv[-1]).resolve()
film = json.loads(gzip.decompress(base64.b64decode(os.environ["FILM_GZ_B64"])))
cache = job.parent.parent / "cache"  # the same place make_video looks
work = job / "work"
work.mkdir(parents=True, exist_ok=True)

if kind == "voice":
    k, n = int(sys.argv[2]), int(sys.argv[3])
    mine = [s for i, s in enumerate(film["shots"]) if i % n == k]
    print(f"voice part {k + 1}/{n}: {len(mine)} lines", flush=True)
    if mine:
        lengths, engine = p.voices({**film, "shots": mine}, work, cache / "voice")
        print(f"made with {engine}: {[round(x, 1) for x in lengths]}", flush=True)
elif kind == "pictures":
    print("pictures:", p.pictures(film, work, cache / "pictures"), flush=True)
else:
    sys.exit(f"unknown part {kind}")
