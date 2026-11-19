"""One part of a video, made on its own GitHub Actions runner so the slow parts run at the same time.

  python part.py mine K N JOB_DIR     1 if voice runner K of N has sentences to make, else 0
  python part.py voice K N JOB_DIR    voice runner K's sentences (voice G, IndicF5 on this runner), to cache/pieces
  python part.py pictures K N JOB_DIR the pictures of shots K, K+N, K+2N, ...
  python part.py draw JOB_DIR         an explainer's scenes, drawn by Claude to estimated timing while the voice is made
  python part.py prepare JOB_DIR      the HyperFrames project (timing, music, shots), from the lines and pictures
  python part.py chunk K N JOB_DIR    render stretch K of N of the film to JOB_DIR/chunk-K.mp4
  python part.py join N JOB_DIR       stitch the stretches, lay the one soundtrack over them, check, preview

Voice lines and pictures land in ./cache, keyed by their text or prompt, where the next steps find them.
The film.json comes in FILM_GZ_B64 (gzip + base64).
"""
import base64
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from shorts import pipeline as p

kind, job = sys.argv[1], Path(sys.argv[-1]).resolve()
film = json.loads(gzip.decompress(base64.b64decode(os.environ["FILM_GZ_B64"])))
LESSON = film.get("format") == "lesson"  # a 16:9 lesson with the 3D host: three.js stage, not HyperFrames
FPS = 30 if LESSON else 24
EN = film.get("lang") == "en"  # narrated in English (Kokoro on this runner's CPU): the Kayal voice runners sit out
cache = job.parent.parent / "cache"  # the same place make_video looks
work, project = job / "work", job / "project"
work.mkdir(parents=True, exist_ok=True)


def duration() -> float:
    if LESSON:
        return float(json.loads((project / "lesson.json").read_text())["dur"])
    return float(re.search(r'data-duration="([\d.]+)"', (project / "index.html").read_text()).group(1))


def sentences(text: str) -> list[tuple[str, float]]:
    """A line in sentences, each with the pause after it: the same cut as indic/tts_server.py makes."""
    breath = {".": 0.42, "!": 0.42, "?": 0.48, "…": 0.6, "...": 0.6}
    out = []
    for m in re.finditer(r"(.+?)(\.\.\.|…|[.!?])(?=\s|$)|(.+?)$", text.strip(), re.S):
        body = (m.group(1) or m.group(3) or "").strip()
        end = m.group(2) or ""
        if body:
            out.append((body + (end if end in ".!?" else ","), breath.get(end, 0.0)))
    return out or [(text, 0.0)]


def piece(ta: str, j: int) -> Path:
    return cache / "pieces" / (hashlib.sha1(f"{p.INDIC_VOICE}|{os.environ.get('INDIC_STEPS', '32')}|{ta}|{j}".encode()).hexdigest()[:16] + ".wav")


def share(k: int, n: int) -> list[tuple[str, int, str]]:
    """Runner k's sentences. Every sentence of the film, longest first, each to the runner with the least text so far:
    the slowest runner, which the whole video waits for, gets as little as possible. Every runner works it out alike."""
    units = sorted(((s["ta"], j, t) for s in film["shots"] for j, (t, _) in enumerate(sentences(s["ta"]))), key=lambda u: -len(u[2]))
    load, mine = [0] * n, []
    for u in units:
        r = load.index(min(load))
        load[r] += len(u[2]) + 20  # each sentence also costs a fixed start-up
        if r == k:
            mine.append(u)
    return mine


def join_voice() -> None:
    """Each line from its sentence pieces, with the pauses and the filter the voice server uses on a whole line,
    into the voice cache, where make_video finds it."""
    for s in film["shots"]:
        f = cache / "voice" / (hashlib.sha1(f"{p.INDIC}|{p.INDIC_VOICE}|{s['mood']}|{s['ta']}".encode()).hexdigest()[:16] + ".mp3")
        if f.exists():
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        lst = work / "pieces.txt"
        rows = []
        for j, (_, pause) in enumerate(sentences(s["ta"])):
            if not piece(s["ta"], j).exists():
                sys.exit(f"voice piece missing: line {s['ta'][:40]}, sentence {j + 1}")
            rows.append(f"file '{piece(s['ta'], j)}'")
            if pause:
                gap = work / f"gap-{pause}.wav"
                if not gap.exists():
                    p.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(pause),
                           "-c:a", "pcm_s16le", str(gap)], "silence")
                rows.append(f"file '{gap}'")
        lst.write_text("\n".join(rows) + "\n")
        m = re.fullmatch(r"([+-]\d+)%", p.PROSODY.get(s["mood"], ("+0%",))[0].strip())
        speed = min(1.06, max(0.94, 1 + int(m.group(1)) / 100)) if m else 1.0
        af = (f"atempo={speed:.3f},silenceremove=start_periods=1:start_threshold=-45dB,"
              "areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,loudnorm=I=-16:TP=-1.5")
        p.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-af", af, "-ar", "24000",
               "-ac", "1", "-b:a", "96k", str(f)], "voice line")


LEAD, GAP_LINE, GAP_SCENE, TAIL = 0.5, 0.35, 0.9, 2.0  # lesson timing: seconds of quiet


def lesson_times(lengths: list[float]) -> tuple[list[float], list[float], float]:
    """Each line's voice start and end: a short breath between lines, a longer one where the scene changes."""
    starts, ends, t = [], [], LEAD
    for i, (s, d) in enumerate(zip(film["shots"], lengths)):
        if i:
            t += GAP_SCENE if s["scene"] != film["shots"][i - 1]["scene"] else GAP_LINE
        starts.append(round(t, 3))
        t += d
        ends.append(round(t, 3))
    return starts, ends, round(t + TAIL, 3)


def stretch(k: int, n: int) -> tuple[float, float]:
    """Stretch k of n, cut on whole frames so the stitched film has no gap or doubled frame."""
    frames = round(duration() * FPS)
    a, b = round(frames * k / n), round(frames * (k + 1) / n)
    return a / FPS, b / FPS


if kind == "mine":
    print(1 if not EN and share(int(sys.argv[2]), int(sys.argv[3])) else 0)

elif kind == "voice":
    # Kayal (indic/kayal_voice.py) was started on this runner before the script existed and has loaded the model;
    # it waits for this runner's sentences, makes them, and marks the file .done (or .failed).
    k, n = int(sys.argv[2]), int(sys.argv[3])
    mine = share(k, n)
    print(f"voice runner {k + 1}/{n}: {len(mine)} sentences, {sum(len(u[2]) for u in mine)} letters", flush=True)
    units = Path(os.path.expanduser("~/units.json"))
    tmp = units.with_suffix(".part")
    tmp.write_text(json.dumps([{"text": text, "out": str(piece(ta, j))} for ta, j, text in mine], ensure_ascii=False))
    tmp.replace(units)
    end = time.monotonic() + 2400
    while not Path(str(units) + ".done").exists():
        if Path(str(units) + ".failed").exists():
            sys.exit("Kayal failed:\n" + Path(str(units) + ".failed").read_text())
        if time.monotonic() > end:
            sys.exit("Kayal took more than 40 minutes")
        time.sleep(2)
    missing = [str(piece(ta, j)) for ta, j, _ in mine if not piece(ta, j).exists()]
    if missing:
        sys.exit(f"voice pieces missing: {missing[:3]}")

elif kind == "pictures":
    k, n = int(sys.argv[2]), int(sys.argv[3])
    # Other runners' shots count as animated here, so every shot keeps its own index and picture seed.
    shots = [s if i % n == k else {**s, "kind": "anim"} for i, s in enumerate(film["shots"])]
    try:
        print("pictures:", p.pictures({**film, "shots": shots}, work, cache / "pictures"), flush=True)
    except p.StepError as e:
        if not LESSON:
            raise
        print("pictures skipped (a lesson shows its 3D scenes without them):", e, flush=True)

elif kind == "draw" and LESSON:
    # The 3D scenes, written by Claude to estimated timing while the voice is made; they time themselves to each
    # line's start (K.at), so prepare's real timing fits them.
    sys.path.insert(0, str(Path(__file__).parent / "lesson"))
    est = [len(s["en"]) / 14 if EN else len(s["ta"]) / 11 + sum(z for _, z in sentences(s["ta"])) for s in film["shots"]]
    a, b, dur = lesson_times(est)
    project.mkdir(parents=True, exist_ok=True)
    (project / "lesson.json").write_text(json.dumps({**p.lesson_json(film, a, b, dur), "draft": True}, ensure_ascii=False, indent=1))
    (project / "env.json").write_text(json.dumps({"fps": 30, "open": [], "beats": []}))
    (project / "assets").mkdir(exist_ok=True)  # the 3D models made for this lesson (models job), by name
    have = sorted(m.name[6:-4] for m in (project / "assets").glob("model-*.glb"))
    (project / "assets" / "models.json").write_text(json.dumps(have))
    print("3D models:", have or "none", "| wanted:", [o["slug"] for o in film.get("objects", [])], flush=True)
    t = time.monotonic()
    usage = p.author_lesson(film, project, lambda s: print("step:", s, flush=True))
    (project / "usage.json").write_text(json.dumps(usage or {}))
    print(f"scenes drawn in {(time.monotonic() - t) / 60:.1f} min", flush=True)

elif kind == "draw":
    # The scenes read their clock from timing.json, so they are drawn now to estimated line lengths (voice G speaks
    # about 11 letters a second, plus each sentence's pause) and prepare rewrites timing.json with the real ones.
    lengths = [len(s["ta"]) / 11 + sum(z for _, z in sentences(s["ta"])) for s in film["shots"]]
    plan_t = p.timeline(film, lengths)

    def quiet(film_, plan_, work_, out):  # no voice yet: a silent track of the right length for Claude's frame checks
        p.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{plan_['duration']:.2f}",
               "-b:a", "96k", str(out)], "silence")
        return plan_["duration"]

    p.mix_audio = quiet
    t = time.monotonic()
    usage = p.author_film(film, plan_t, work, project, lambda s: print("step:", s, flush=True))
    print(f"drawn in {(time.monotonic() - t) / 60:.1f} min", flush=True)

elif kind == "prepare":
    t = time.monotonic()
    if os.environ.get("SHORTS_BACKUP_VOICE") == "1" and not EN:  # voice G: the sentences came from the voice runners
        join_voice()
    if EN:
        lengths, engine = p.english_voices(film, work, cache / "voice"), "Kokoro (English, af_heart)"
    else:
        lengths, engine = p.voices(film, work, cache / "voice")
    sources = p.pictures(film, work, cache / "pictures")
    if LESSON:
        sys.path.insert(0, str(Path(__file__).parent / "lesson"))
        from envelope import envelope
        if not (project / "stations.js").exists():
            sys.exit("the 3D scenes were not drawn")
        a, b, dur = lesson_times(lengths)
        plan_t = {"duration": dur, "shots": [{"voiceStart": x, "voiceEnd": y} for x, y in zip(a, b)]}
        (project / "assets").mkdir(parents=True, exist_ok=True)
        p.mix_audio(film, plan_t, work, project / "assets" / "voice.mp3")
        p.lesson_kit(project)
        for i, sh in enumerate(film["shots"]):  # each scene's AI picture, where the stage finds it
            if sh.get("kind") == "photo" and (work / f"shot-{i}.jpg").exists():
                shutil.copy(work / f"shot-{i}.jpg", project / "assets" / f"pic-{sh['scene']}.jpg")
        (project / "lesson.json").write_text(json.dumps(p.lesson_json(film, a, b, dur), ensure_ascii=False, indent=1))
        (project / "env.json").write_text(json.dumps(envelope(str(work / "voice.wav"))))
        (project / "timing.json").write_text(json.dumps(plan_t))  # the captions' clock (brain.py done)
        scenes = film["shots"][-1]["scene"] + 1
        (job / "prepared.json").write_text(json.dumps({"voice": engine, "picture_sources": {"3D scenes": scenes}, "shots": len(film["shots"]),
                                                       "theme": "lesson", "prepare_minutes": round((time.monotonic() - t) / 60, 1)}))
        print(f"prepared: {dur:.1f}s lesson, {scenes} scenes, voice {engine}", flush=True)
        sys.exit(0)
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

elif kind == "chunk" and LESSON:
    k, n = int(sys.argv[2]), int(sys.argv[3])
    frames = round(duration() * FPS)
    a, b = round(frames * k / n), round(frames * (k + 1) / n)
    print(f"render stretch {k + 1}/{n}: frames {a} to {b}", flush=True)
    t = time.monotonic()
    p.run([sys.executable, str(Path(__file__).parent / "lesson" / "capture.py"), str(project), "chunk", str(a), str(b), str(job / f"chunk-{k}.mp4")], "3D render")
    print(f"stretch {k + 1}: {p.probe(job / f'chunk-{k}.mp4'):.2f}s rendered in {(time.monotonic() - t) / 60:.1f} min", flush=True)

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
    mbps = (job / "video.mp4").stat().st_size * 8 / 1e6 / max(1.0, duration())
    cap = 8 if LESSON else 6  # Mbps. n8n holds the whole file in memory on its way to YouTube: a 280 MB video crashed it
    if mbps > cap + 1:
        big = job / "video-big.mp4"
        (job / "video.mp4").replace(big)
        p.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(big), "-c:v", "libx264", "-preset", "medium", "-crf", "20" if LESSON else "23",
               "-maxrate", f"{cap}M", "-bufsize", f"{2 * cap}M", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(job / "video.mp4")], "shrink")
        big.unlink()
        print(f"shrunk from {mbps:.1f} Mbps", flush=True)
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
