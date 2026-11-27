"""Claude's desk work for the Know This Daily studio, on a GitHub runner. The studio (n8n) keeps every piece of data;
this runner fetches one request, does it, sends the answer back and forgets it.

  python brain.py REQ                 a plan, a plan edit, ideas from the channel stats, or today's news picks
  python brain.py film REQ JOB_DIR    the shot list for a video (write, rewrite after a failure, or edit), to JOB_DIR/film.json
  python brain.py done JOB_DIR        tell the studio the video is made: facts, captions, what it said (for the library)

STUDIO_URL is the studio API webhook (its path is the secret). Ported from the old box's api.py, same rules.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from shorts import pipeline as p

STUDIO = os.environ.get("STUDIO_URL", "")
WORD = re.compile(r"[\w஀-௿]{2,}")  # 2+: "AI", "TV" count
STOP = set("the and for with that this what about make video videos part next from into how why are was were you your "
           "can will its new one more like is of to in on it an as at be by do my me we or so up".split())


def studio(path: str, body: dict | None = None) -> dict:
    """GET (no body) or POST to the studio API. path is like /gh/input&req=ID (query joined with &)."""
    if path == "/gh/render" and body is not None:  # which run reports: the studio ignores a replaced run
        body = {**body, "run": os.environ.get("GITHUB_RUN_ID", "")}
    req = urllib.request.Request(f"{STUDIO}?p={path}", method="POST" if body is not None else "GET",
                                 data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "know-this-daily-runner"})
    for i in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except Exception:  # noqa: BLE001 - n8n busy for a moment: try again
            if i == 4:
                raise
            time.sleep(10 * (i + 1))
    return {}


def safe(text: str) -> str:
    """Text Telegram shows the same in plain, Markdown or HTML mode."""
    return text.replace("&", "and").replace("<", "(").replace(">", ")")


# ---------------------------------------------------------------- the library (rows built by the studio from its jobs)

def related(query: str, lib: list[dict], n: int = 5) -> list[dict]:
    """The library entries that best match a request: word overlap, topic and series count triple.
    "last video" / "previous" / "yesterday" with no match falls back to the newest videos."""
    q = {w for w in WORD.findall(query.lower()) if w not in STOP}
    scored = []
    for r in lib:
        head = set(WORD.findall(f"{r['topic']} {r['series']} {r['title']}".lower()))
        body = set(WORD.findall(r["said"].lower()))
        score = 3 * len(q & head) + len(q & body)
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])  # stable: equal scores stay newest first
    hits = [r for _, r in scored[:n]]
    if not hits and re.search(r"\b(last|previous|yesterday|earlier|part\s*\d|next part|continue|follow.?up)\b", query, re.I):
        hits = lib[:2]
    return hits


def results(stats: dict, lib: list[dict]) -> list[dict]:
    """The last YouTube numbers per video, joined to the library for category and format. Best views per day first."""
    kind = {v: r for r in lib for v in r.get("video_ids", [])}
    rows = []
    for v in stats.get("videos", []):
        try:
            days = max((datetime.now(timezone.utc) - datetime.fromisoformat(v["at"].replace("Z", "+00:00"))).total_seconds() / 86400, 0.5)
        except (KeyError, ValueError):
            days = 1.0
        r = kind.get(v["id"], {})
        rows.append({**v, "days": days, "per_day": v["views"] / days, "category": r.get("category", ""), "format": r.get("format", ""),
                     "name": v["title"].split("|")[-1].strip() or v["title"]})
    return sorted(rows, key=lambda r: r["per_day"], reverse=True)


def result_lines(stats: dict, lib: list[dict]) -> list[str]:
    return [f"\"{r['name']}\" | {r['category'] or ('kids' if r['kids'] else 'unknown')}, {r['format'] or 'unknown format'} | "
            f"{r['views']} views in {r['days']:.1f} days ({r['per_day']:.0f}/day), {r['likes']} likes, {r['comments']} comments"
            for r in results(stats, lib) if r["days"] >= 0.5 and r["views"] + r["likes"] > 2]


def series_parts(lib: list[dict], series: str, part: int) -> list[dict]:
    """The earlier parts of a series, oldest first, for the script writer."""
    if not series:
        return []
    mine = [r for r in lib if r["series"].lower() == series.lower() or r["topic"].lower() == series.lower()]
    return sorted([r for r in mine if r["part"] < part], key=lambda r: r["part"])[-3:]


# ---------------------------------------------------------------- the jobs

def think(inp: dict) -> dict:
    op, lib = inp["op"], inp.get("lib") or []
    if op == "plan":
        idea = inp.get("idea") or None
        found = related(idea or "", lib) if idea else []
        first = next((r for r in lib if r["job"] == inp.get("first")), None)
        if first:  # ➕ Next part: that exact video leads
            found = [first] + [r for r in found if r["job"] != first["job"]]
        plan, usage = p.make_plan(idea, inp.get("made") or [], inp.get("feedback") or [], found,
                                  None if idea else result_lines(inp.get("stats") or {}, lib))
        return {"plan": plan, "usage": usage}
    if op == "revise_plan":
        found = related(f"{inp.get('idea') or ''} {inp['change']}", lib)
        plan, usage = p.revise_plan(inp["plan"], inp["change"], inp.get("idea"), inp.get("changes") or [], found)
        return {"plan": plan, "usage": usage}
    if op == "news":  # 📰 today's world news: Claude's 3 best stories for a video, from the feeds' own facts
        stories, usage = p.latest_news(inp.get("made") or [])
        return {"stories": stories, "usage": usage}
    if op == "ideas":
        stats = inp.get("stats") or {}
        d, usage = p.next_ideas(result_lines(stats, lib), inp.get("made") or [],
                                [f"on \"{c['video']}\": {c['text']}" for c in stats.get("comments", [])])
        text = ("💡 <b>What to make next</b>\n\n" + safe(d["reading"]) + "\n\n"
                + "\n\n".join(f"{i}. <code>{safe(x['idea'])}</code>\n{safe(x['why'])}" for i, x in enumerate(d["ideas"], 1))
                + "\n\nTap an idea to copy it, then send it to me to get its plan.")
        return {"text": text, "usage": usage}
    raise p.StepError(f"unknown request {op}")


def meta_of(film: dict) -> dict:
    meta = {k: film[k] for k in ("title", "description", "hashtags", "tags")}
    meta["en_title"] = film.get("en_title") or film["title"].split("|")[-1].strip()
    meta["en_description"] = film.get("en_description") or film["description"]
    meta["en_hashtags"] = film.get("en_hashtags") or [h for h in film["hashtags"] if "tamil" not in h.lower()]
    meta["tag_source"] = film.get("tag_source", "")
    meta["sound_note"] = p.sound_note(film)  # what an edit set for the sound, shown to the owner with the video
    meta["for_kids"] = bool(film.get("for_kids"))  # sets YouTube's "Made for Kids" on upload
    meta["category"] = film.get("category") or ("kids" if meta["for_kids"] else "education")
    meta["category_id"] = p.YT_CATEGORY.get(meta["category"], "27")
    meta["has_en"] = False
    meta["lang"] = film.get("lang") or "ta"  # the spoken language: the upload's default language
    return meta


def film(req: str, job: Path) -> None:
    """The shot list: an edit of the last one, the last one again (a retry costs no Claude call), or a new one."""
    inp = studio(f"/gh/input&req={req}")
    job.mkdir(parents=True, exist_ok=True)
    old = Path("prev/film.json")
    usage = None
    if inp.get("action") == "revise" and old.exists():
        f, usage = p.revise_film(json.loads(old.read_text()), inp["change"])
    elif inp.get("action") == "retry" and old.exists():
        f = json.loads(old.read_text())
    else:
        pl = inp["plan"]
        if inp.get("shape") == "video":  # the owner tapped 🖥 Video: a 16:9 lesson with the 3D host
            pl = {**pl, "format": "lesson"}
        f, usage = p.write_film(pl, series_parts(inp.get("lib") or [], pl.get("series", ""), int(pl.get("part") or 1)))
    (job / "film.json").write_text(json.dumps(f, ensure_ascii=False, indent=1))
    step = "voice and 3D scenes" if f.get("format") == "lesson" else "pictures and voice"
    studio("/gh/render", {"job": inp["job"], "step": step, "meta": {**meta_of(f), "shape": "video" if f.get("format") == "lesson" else "short"}, "usage": usage})
    print(f"film: {f.get('title')} | {f.get('format')} | {len(f['shots'])} shots", flush=True)


def captions_srt(film: dict, timed: dict, words: int = 8) -> str:
    """English closed captions (SRT) for the Tamil video: each line's English text over its voice time, in short cues."""
    def ts(t: float) -> str:
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    cues = []
    for shot, t in zip(film.get("shots", []), [x for x in timed.get("shots", []) if "voiceStart" in x]):
        w = re.sub(r"\*", "", shot.get("en", "")).split()
        if not w:
            continue
        a, b = float(t["voiceStart"]), float(t["voiceEnd"])
        n = -(-len(w) // words)  # cues needed, then even sizes so no cue is a lone word
        size = -(-len(w) // n)
        parts = [w[i:i + size] for i in range(0, len(w), size)]
        for k, part in enumerate(parts):  # time split by word count, so a cue stays on while its words are spoken
            s0 = a + (b - a) * sum(len(x) for x in parts[:k]) / len(w)
            s1 = a + (b - a) * sum(len(x) for x in parts[:k + 1]) / len(w)
            cues.append((s0, s1, " ".join(part)))
    return "\n".join(f"{i}\n{ts(x)} --> {ts(y)}\n{text}\n" for i, (x, y, text) in enumerate(cues, 1))


def timing(project: Path) -> dict:
    """Each line's voice times: assets/film.js for a picture film, timing.json for a drawn explainer."""
    if (project / "timing.json").exists():
        return json.loads((project / "timing.json").read_text())
    js = (project / "assets/film.js").read_text()
    return json.loads(js[js.index("{"):js.rindex("}") + 1])


def done(job: Path) -> None:
    f = json.loads((job / "film.json").read_text())
    facts = json.loads((job / "facts.json").read_text())
    caps = captions_srt(f, timing(job / "project"))
    lib = {"said": " ".join(re.sub(r"\*", "", s.get("en", "")) for s in f.get("shots", [])),
           "series": f.get("series") or "", "part": int(f.get("part") or 1), "category": f.get("category") or "",
           "format": f.get("format", "")}
    facts.pop("ok", None)
    facts["render"] = "github"
    if os.environ.get("THUMB_ARTIFACT", "").isdigit():  # the thumbnail's GitHub artifact: the bot shows it and sets it on YouTube
        facts["thumb"] = int(os.environ["THUMB_ARTIFACT"])
    studio("/gh/render", {"job": job.name, "ok": True, "facts": facts, "lib": lib, "captions": caps})


if __name__ == "__main__":
    if sys.argv[1] == "film":
        film(sys.argv[2], Path(sys.argv[3]).resolve())
    elif sys.argv[1] == "done":
        done(Path(sys.argv[2]).resolve())
    else:
        req = sys.argv[1]
        try:
            out = {"ok": True, **think(studio(f"/gh/input&req={req}"))}
        except Exception as e:  # noqa: BLE001 - the studio tells the person what went wrong
            traceback.print_exc()
            out = {"ok": False, "error": (str(e) if isinstance(e, p.StepError) else f"{type(e).__name__}: {e}")[:1500]}
        studio("/gh/result", {"req": req, **out})
        sys.exit(0 if out["ok"] else 1)
