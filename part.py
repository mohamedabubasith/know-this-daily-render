"""One part of a video, made on its own GitHub Actions runner so the slow parts run at the same time.

  python part.py voice K N JOB_DIR    voice lines K, K+N, K+2N, ... (voice G, IndicF5 on this runner)
  python part.py pictures JOB_DIR     every picture
  python part.py prepare JOB_DIR      the HyperFrames project (timing, music, shots), from the lines and pictures
  python part.py chunk K N JOB_DIR    render stretch K of N of the film to JOB_DIR/chunk-K.mp4
  python part.py join N JOB_DIR       stitch the stretches, lay the one soundtrack over them, check, preview

Voice lines and pictures land in ./cache, keyed by their text or prompt, where the next steps find them.
The film.json comes in FILM_GZ_B64 (gzip + base64).
"""
import base64
import gzip
import json
import os
import re
import sys
import time
from pathlib import Path

from shorts import pipeline as p

FPS = 24
kind, job = sys.argv[1], Path(sys.argv[-1]).resolve()
film = json.loads(gzip.decompress(base64.b64decode(os.environ["FILM_GZ_B64"])))
cache = job.parent.parent / "cache"  # the same place make_video looks
work, project = job / "work", job / "project"
work.mkdir(parents=True, exist_ok=True)


def duration() -> float:
    return float(re.search(r'data-duration="([\d.]+)"', (project / "index.html").read_text()).group(1))


def stretch(k: int, n: int) -> tuple[float, float]:
    """Stretch k of n, cut on whole frames so the stitched film has no gap or doubled frame."""
    frames = round(duration() * FPS)
    a, b = round(frames * k / n), round(frames * (k + 1) / n)
    return a / FPS, b / FPS


if kind == "voice":
    k, n = int(sys.argv[2]), int(sys.argv[3])
    mine = [s for i, s in enumerate(film["shots"]) if i % n == k]
    print(f"voice part {k + 1}/{n}: {len(mine)} lines", flush=True)
    if mine:
        lengths, engine = p.voices({**film, "shots": mine}, work, cache / "voice")
        print(f"made with {engine}: {[round(x, 1) for x in lengths]}", flush=True)

elif kind == "pictures":
    print("pictures:", p.pictures(film, work, cache / "pictures"), flush=True)

elif kind == "prepare":
    t = time.monotonic()
    lengths, engine = p.voices(film, work, cache / "voice")
    sources = p.pictures(film, work, cache / "pictures")
    plan_t = p.timeline(film, lengths)
    if film.get("format") == "explainer":  # drawn by Claude to the finished voice
        p.author_film(film, plan_t, work, project, lambda s: print("step:", s, flush=True))
        sources = {"drawn": len(film["shots"])}
    else:
        p.assemble(film, plan_t, lengths, work, project)
    lint = p.hyperframes(project, "lint")
    m = re.search(r"(\d+) error", lint)
    if m and int(m.group(1)):
        sys.exit("the film has errors:\n" + lint[-900:])
    (job / "prepared.json").write_text(json.dumps({"voice": engine, "picture_sources": sources, "shots": len(film["shots"]),
                                                   "theme": plan_t.get("theme"), "prepare_minutes": round((time.monotonic() - t) / 60, 1)}))
    print(f"prepared: {duration():.1f}s film, voice {engine}, theme {plan_t.get('theme')}", flush=True)

elif kind == "chunk":
    k, n = int(sys.argv[2]), int(sys.argv[3])
    a, b = stretch(k, n)
    print(f"render stretch {k + 1}/{n}: {a:.3f}s to {b:.3f}s", flush=True)
    p.hyperframes(project, "render", "--quality", os.environ.get("SHORTS_QUALITY", "looks"), "--fps", str(FPS),
                  "--start", f"{a:.4f}", "--end", f"{b:.4f}", "-o", str(job / f"chunk-{k}.mp4"))
    print(f"stretch {k + 1}: {p.probe(job / f'chunk-{k}.mp4'):.2f}s rendered", flush=True)

elif kind == "join":
    n = int(sys.argv[2])
    parts = [job / f"chunk-{k}.mp4" for k in range(n)]
    missing = [x.name for x in parts if not x.exists()]
    if missing:
        sys.exit(f"missing stretches: {missing}")
    (job / "chunks.txt").write_text("".join(f"file '{x}'\n" for x in parts))
    sound = project / "assets" / "voice.mp3"
    # The picture is stitched without re-encoding; the soundtrack is laid over whole, so the joins never click.
    p.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(job / "chunks.txt"), "-i", str(sound),
           "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration():.3f}",
           "-movflags", "+faststart", str(job / "video.mp4")], "join")
    got, want = p.probe(job / "video.mp4"), duration()
    facts = json.loads((job / "prepared.json").read_text())
    if abs(got - want) > 0.5 or not p.has_audio(job / "video.mp4"):
        facts.update(ok=False, error=f"joined video is {got:.1f}s for a {want:.1f}s film, or has no sound")
    else:
        p.preview(job / "video.mp4", job / "preview.mp4", got)
        facts.update(ok=True, seconds=round(got, 1), size_mb=round((job / "video.mp4").stat().st_size / 1e6, 1),
                     preview_mb=round((job / "preview.mp4").stat().st_size / 1e6, 1))
    (job / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1))
    print(json.dumps(facts, ensure_ascii=False), flush=True)
    sys.exit(0 if facts["ok"] else 1)

else:
    sys.exit(f"unknown part {kind}")
