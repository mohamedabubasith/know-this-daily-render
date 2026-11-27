"""Know This Daily: plan -> shot list -> pictures + Tamil voice -> HyperFrames film -> MP4.

Claude writes only JSON (a plan, then a shot list). Everything else is plain code, so a run either
produces a checked video or fails loudly with the step that broke.

    python -m shorts.pipeline plan "why is the sky blue"       # print a plan
    python -m shorts.pipeline film plan.json out_dir             # full film from a plan
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import datetime
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
PROMPTS = HERE / "prompts"
TEMPLATE = HERE / "template"
CONFIG = Path(os.environ.get("SHORTS_CONFIG", Path.home() / ".config/shorts"))
MODEL = os.environ.get("SHORTS_MODEL", "sonnet")
PLAN_MODEL = os.environ.get("SHORTS_PLAN_MODEL", "sonnet")  # Haiku followed the rules over the owner's words
HYPERFRAMES = os.environ.get("SHORTS_HYPERFRAMES", "hyperframes@0.9.40")
RENDER = os.environ.get("SHORTS_RENDER", "local")  # "github": videos are made by the public render repo's Actions
W, H = 1080, 1920

MOODS = ["mysterious", "dramatic", "happy", "sad", "excited", "calm", "curious", "epic", "tense"]
MOVES = ["push_in", "pull_out", "pan_left", "pan_right", "tilt_up", "tilt_down", "drift", "crash_zoom", "orbit"]
FRAMINGS = ["wide", "medium", "close", "extreme_close", "aerial", "low_angle"]
TRANSITIONS = ["cut", "whip", "zoom", "flash", "dip", "fade", "iris"]
ANIMS = ["diagram", "chart", "timeline", "scale", "stat", "orbit", "wave", "globe"]
VOICES = {"female": "ta-IN-PallaviNeural", "male": "ta-IN-ValluvarNeural"}
# How each mood is spoken: edge-tts rate and pitch.
PROSODY = {
    "mysterious": ("-3%", "-4Hz"), "dramatic": ("-1%", "-6Hz"), "happy": ("+11%", "+5Hz"),
    "sad": ("-7%", "-8Hz"), "excited": ("+15%", "+7Hz"), "calm": ("+1%", "+0Hz"),
    "curious": ("+8%", "+3Hz"), "epic": ("+0%", "-3Hz"), "tense": ("+7%", "-2Hz"),
}
EXPLAINER_HOLD = 1.2  # seconds an explainer rests on each finished drawing, voice silent (the owner asked for this)
LEAD, GAP, END_HOLD, END_CARD = 0.3, 0.55, 0.6, 2.7  # GAP: a breath between shots, like an edited voice-over
# Seconds each transition shows the incoming shot before the cut point.
PRE = {"fade": 0.6, "whip": 0.3, "zoom": 0.35, "iris": 0.45}
# Sound settings an edit can change (film["sound"]): voice_start = seconds before the first spoken word,
# gap = seconds of quiet between two lines, music = on / soft / off. Defaults per format: (voice_start, gap).
SOUND_DEFAULTS = {"explainer": (LEAD, EXPLAINER_HOLD + 0.45), "lesson": (0.5, 0.35)}
MUSIC_LEVEL = {"on": 1.0, "soft": 0.4, "off": 0.0}


def sound_of(film: dict) -> dict:
    """The film's sound settings: what an edit set, over the defaults of its format, kept inside sane limits."""
    lead, gap = SOUND_DEFAULTS.get(film.get("format"), (LEAD, GAP))
    s = film.get("sound") or {}
    music = s.get("music") if s.get("music") in MUSIC_LEVEL else "on"
    return {"voice_start": round(min(max(float(s.get("voice_start", lead)), 0.0), 8.0), 2),
            "gap": round(min(max(float(s.get("gap", gap)), 0.15), 4.0), 2), "music": music}


def sound_note(film: dict) -> str:
    """The sound settings an edit set, in plain words for the owner ('' when none)."""
    s, cur = film.get("sound") or {}, sound_of(film)
    say = {"voice_start": "voice starts at {:g} s", "gap": "{:g} s between lines", "music": "music {}"}
    return ", ".join(text.format(cur[k]) for k, text in say.items() if k in s)


class StepError(RuntimeError):
    """A pipeline step failed; the message says which and why, in plain words."""


class Cancelled(StepError):
    """The owner cancelled the film; raised at the next checkpoint."""


should_stop = lambda: False  # noqa: E731 - the API swaps in a check for the running job


# ---------------------------------------------------------------- Claude

FORMATS = ["explainer", "facts", "story"]  # fully animated / pictures + some animation / kids storybook

CATEGORIES = ["education", "entertainment", "kids", "inspiration"]
YT_CATEGORY = {"education": "27", "entertainment": "24", "kids": "1", "inspiration": "22"}  # YouTube category ids

PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["understood", "topic", "category", "format", "subtitles", "for_kids", "audience", "notes", "series", "part",
                 "angle", "hook", "points", "title_idea", "why"],
    "properties": {
        "understood": {"type": "string"},
        "category": {"enum": CATEGORIES},
        "format": {"enum": FORMATS},
        "subtitles": {"enum": ["ta", "en"]},
        "for_kids": {"type": "boolean"},
        "audience": {"type": "string"}, "notes": {"type": "string"},
        "series": {"type": "string"}, "part": {"type": "integer", "minimum": 1, "maximum": 50},
        "topic": {"type": "string"}, "angle": {"type": "string"}, "hook": {"type": "string"},
        "points": {"type": "array", "minItems": 3, "maxItems": 6, "items": {"type": "string"}},
        "title_idea": {"type": "string"}, "why": {"type": "string"},
    },
}
SHOT = {
    "type": "object", "additionalProperties": False,
    "required": ["kind", "ta", "en", "image", "anim", "framing", "move", "transition", "mood", "overlay"],
    "properties": {
        "kind": {"enum": ["photo", "anim"]},
        "ta": {"type": "string"}, "en": {"type": "string"}, "image": {"type": "string"},
        "anim": {
            "type": "object", "additionalProperties": False,
            "required": ["type", "title", "variant", "unit", "lat", "lon", "items"],
            "properties": {
                "type": {"enum": ANIMS}, "title": {"type": "string"}, "variant": {"type": "string"}, "unit": {"type": "string"},
                "lat": {"type": "number"}, "lon": {"type": "number"},
                "items": {"type": "array", "maxItems": 5, "items": {
                    "type": "object", "additionalProperties": False, "required": ["label", "value", "note"],
                    "properties": {"label": {"type": "string"}, "value": {"type": "number"}, "note": {"type": "string"}}}},
            },
        },
        "framing": {"enum": FRAMINGS}, "move": {"enum": MOVES}, "transition": {"enum": TRANSITIONS},
        "mood": {"enum": MOODS},
        "overlay": {
            "type": "object", "additionalProperties": False, "required": ["kind", "text", "value", "suffix"],
            "properties": {"kind": {"enum": ["none", "big_text", "counter", "label"]}, "text": {"type": "string"},
                           "value": {"type": "number"}, "suffix": {"type": "string"}},
        },
    },
}
THUMB = {  # the thumbnail: its few big words, a supporting line (16:9 only) and the shot whose picture it uses
    "type": "object", "additionalProperties": False, "required": ["words", "line", "shot"],
    "properties": {"words": {"type": "string"}, "line": {"type": "string"}, "shot": {"type": "integer"}},
}
FILM_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["thumb", "hook", "title", "description", "hashtags", "tags", "en_title", "en_description", "en_hashtags",
                 "voice", "style", "for_kids", "shots"],
    "properties": {
        "for_kids": {"type": "boolean"},
        "hook": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "en_title": {"type": "string"}, "en_description": {"type": "string"},
        "en_hashtags": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "voice": {"enum": ["female", "male"]}, "style": {"type": "string"}, "thumb": THUMB,
        "shots": {"type": "array", "minItems": 7, "maxItems": 14, "items": SHOT},
    },
}


EXPLAINER_SHOT = {
    "type": "object", "additionalProperties": False,
    "required": ["ta", "en", "mood", "picture"],
    "properties": {"ta": {"type": "string"}, "en": {"type": "string"}, "mood": {"enum": MOODS}, "picture": {"type": "string"}},
}
EXPLAINER_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["format", "thumb", "hook", "title", "description", "hashtags", "tags", "en_title", "en_description",
                 "en_hashtags", "voice", "for_kids", "shots"],
    "properties": {
        "format": {"enum": ["explainer"]}, "for_kids": {"type": "boolean"},
        "hook": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}}, "tags": {"type": "array", "items": {"type": "string"}},
        "en_title": {"type": "string"}, "en_description": {"type": "string"},
        "en_hashtags": {"type": "array", "items": {"type": "string"}},
        "voice": {"enum": ["female", "male"]}, "thumb": THUMB,
        "shots": {"type": "array", "minItems": 6, "maxItems": 11, "items": EXPLAINER_SHOT},
    },
}
POSES = ["open", "wide", "present", "point", "one", "chest", "think", "shrug", "wave", "rest"]
LESSON_SHOT = {
    "type": "object", "additionalProperties": False,
    "required": ["ta", "en", "mood", "scene", "picture", "objects", "act"],
    "properties": {"ta": {"type": "string"}, "en": {"type": "string"}, "mood": {"enum": MOODS},
                   "scene": {"type": "integer", "minimum": 0, "maximum": 15}, "picture": {"type": "string"},
                   "objects": {"type": "array", "maxItems": 3, "items": {  # real things, made as real 3D models
                       "type": "object", "additionalProperties": False, "required": ["name", "look"],
                       "properties": {"name": {"type": "string"}, "look": {"type": "string"}}}},
                   "act": {"type": "array", "maxItems": 2, "items": {
                       "type": "object", "additionalProperties": False, "required": ["at", "pose", "face"],
                       "properties": {"at": {"type": "number", "minimum": 0, "maximum": 0.9}, "pose": {"enum": POSES},
                                      "face": {"enum": ["", "sad"]}}}}},
}
LESSON_INTRO = {  # the host in the centre says what today's lesson covers, then moves right as scene 0 starts
    "type": "object", "additionalProperties": False, "required": ["lines", "agenda"],
    "properties": {
        "lines": {"type": "array", "minItems": 2, "maxItems": 2, "items": {
            "type": "object", "additionalProperties": False, "required": ["ta", "en", "mood", "act"],
            "properties": {k: LESSON_SHOT["properties"][k] for k in ("ta", "en", "mood", "act")}}},
        "agenda": {"type": "array", "minItems": 3, "maxItems": 3, "items": {
            "type": "object", "additionalProperties": False, "required": ["ta", "en"],
            "properties": {"ta": {"type": "string"}, "en": {"type": "string"}}}},
    },
}
LESSON_SCHEMA = {  # a 16:9 lesson with the 3D host (the owner's "Video" button)
    "type": "object", "additionalProperties": False,
    "required": ["hook", "title", "description", "hashtags", "tags", "en_title", "en_description", "en_hashtags",
                 "voice", "for_kids", "intro", "shots", "thumb"],
    "properties": {
        "intro": LESSON_INTRO, "thumb": THUMB,
        "for_kids": {"type": "boolean"},
        "hook": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}}, "tags": {"type": "array", "items": {"type": "string"}},
        "en_title": {"type": "string"}, "en_description": {"type": "string"},
        "en_hashtags": {"type": "array", "items": {"type": "string"}},
        "voice": {"enum": ["female", "male"]},
        "shots": {"type": "array", "minItems": 12, "maxItems": 36, "items": LESSON_SHOT},
    },
}
NO_ANIM = {"type": "stat", "title": "", "variant": "", "unit": "", "lat": 0, "lon": 0, "items": []}
NO_OVERLAY = {"kind": "none", "text": "", "value": 0, "suffix": ""}


def claude_token() -> str:
    token = "".join((os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or (CONFIG / "claude-token").read_text()).split())  # a pasted token may carry spaces or a newline
    if not token:
        raise StepError("no Claude token: put it in ~/.config/shorts/claude-token")
    return token


def claude_json(system: str, prompt: str, schema: dict, step: str, model: str = MODEL, think: bool = True) -> tuple[dict, dict]:
    """One Claude call with no tools, answering in JSON that matches `schema`. Returns (data, usage)."""
    env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": claude_token(), "DISABLE_AUTOUPDATER": "1",
           **({} if think else {"MAX_THINKING_TOKENS": "0"}),  # a short plan needs no thinking tokens
           "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    cmd = ["claude", "-p", prompt, "--model", model, "--tools", "", "--output-format", "json",
           "--json-schema", json.dumps(schema), "--system-prompt", system,
           "--no-session-persistence", "--strict-mcp-config"]
    last = ""
    for attempt in range(2):
        # An empty folder outside the home directory, so no project instructions are picked up.
        with tempfile.TemporaryDirectory(prefix="shorts-claude-") as cwd:
            done = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
        try:
            out = json.loads(done.stdout)
        except json.JSONDecodeError:
            last = (done.stderr or done.stdout)[-400:]
            continue
        if out.get("is_error"):
            last = str(out.get("result"))[:400]
            continue
        data = out.get("structured_output")
        if data is None:
            text = out.get("result") or ""
            m = re.search(r"\{.*\}", text, re.S)
            try:
                data = json.loads(m.group(0)) if m else None
            except json.JSONDecodeError:
                data = None
        if isinstance(data, dict):
            u = out.get("usage") or {}
            usage = {
                "step": step, "model": model, "cost_usd": round(out.get("total_cost_usd") or 0, 4),
                "input_tokens": u.get("input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
                "cache_read_tokens": u.get("cache_read_input_tokens", 0),
                "cache_write_tokens": u.get("cache_creation_input_tokens", 0),
                "seconds": round((out.get("duration_ms") or 0) / 1000, 1),
            }
            return data, usage
        last = "Claude did not return JSON"
    raise StepError(f"Claude ({step}) failed: {last}")


def _library_block(related: list[dict]) -> str:
    """Videos already made that match the request: the planner's knowledge base for follow-ups and part 2s."""
    if not related:
        return "Channel library (videos already made that match this request): none found."
    rows = [f"- {r['date'][:10]} \"{r['title']}\" | topic: {r['topic']} | series: {r['series'] or 'none'}, part {r['part']} | "
            f"{r['category']}, {r['format']}\n  What it said: {r['said'][:700]}" for r in related]
    return "Channel library (videos already made that match this request, newest first):\n" + "\n".join(rows)


def results_block(results: list[str]) -> str:
    return ("Channel results (YouTube numbers of our videos, best first; a small sample, so a hint and not a rule):\n"
            + ("\n".join(f"- {r}" for r in results[:30]) or "- no numbers yet"))


IDEAS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["reading", "ideas"], "properties": {
    "reading": {"type": "string"},
    "ideas": {"type": "array", "minItems": 3, "maxItems": 3, "items": {
        "type": "object", "additionalProperties": False, "required": ["idea", "why"],
        "properties": {"idea": {"type": "string"}, "why": {"type": "string"}}}}}}


def next_ideas(results: list[str], made: list[str], comments: list[str] | None = None) -> tuple[dict, dict]:
    """Three next-video ideas from the channel's own numbers and what viewers wrote."""
    prompt = results_block(results) + "\n\nAlready made (never repeat):\n" + ("\n".join(f"- {t}" for t in made[-40:]) or "- nothing yet")
    prompt += "\n\nViewer comments, newest first (requests and questions here are strong hints):\n" + ("\n".join(f"- {c[:300]}" for c in (comments or [])[:20]) or "- none yet")
    return claude_json((PROMPTS / "ideas.md").read_text(), prompt, IDEAS_SCHEMA, "ideas", PLAN_MODEL, think=False)


def make_plan(idea: str | None, made: list[str], feedback: list[str], related: list[dict] | None = None,
              results: list[str] | None = None) -> tuple[dict, dict]:
    prompt = (f"The owner's request, in their own words:\n\"\"\"\n{idea}\n\"\"\"" if idea
              else "No idea given: choose today's topic yourself.")
    prompt += "\n\n" + _library_block(related or [])
    prompt += "\n\nAlready made (do not repeat unless the owner asks for a next part):\n" + ("\n".join(f"- {t}" for t in made[-40:]) or "- nothing yet")
    prompt += "\n\nOwner feedback on earlier plans and videos:\n" + ("\n".join(f"- {f[:160]}" for f in feedback[-10:]) or "- none yet")
    if results:
        prompt += "\n\n" + results_block(results)
    return claude_json((PROMPTS / "plan.md").read_text(), prompt, PLAN_SCHEMA, "plan", PLAN_MODEL, think=False)


def revise_plan(plan: dict, change: str, idea: str | None = None, earlier: list[str] | None = None,
                related: list[dict] | None = None) -> tuple[dict, dict]:
    prompt = (f"The owner's original request:\n\"\"\"\n{idea or '(daily topic, no request)'}\n\"\"\"\n\n"
              + ("Changes the owner already asked for, in order:\n" + "\n".join(f"- {c}" for c in earlier) + "\n\n" if earlier else "")
              + f"Current plan:\n{json.dumps(plan, ensure_ascii=False, indent=1)}\n\n"
              + _library_block(related or []) + "\n\n"
              + f"The owner now says:\n\"\"\"\n{change}\n\"\"\"\n\n"
              "Apply exactly what the owner says, even if it differs from the default rules (topic, audience, tone, depth, "
              "format, length, category, series). Keep everything else. Put every instruction of theirs that the writer must "
              "follow into notes, and restate in understood what they want. Return the full revised plan.")
    return claude_json((PROMPTS / "plan.md").read_text(), prompt, PLAN_SCHEMA, "plan-edit", PLAN_MODEL, think=False)


def _add_usage(a: dict, b: dict) -> dict:
    out = dict(a)
    for k in ("cost_usd", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "seconds"):
        out[k] = round(a.get(k, 0) + b.get(k, 0), 4)
    out["step"] = f"{a['step']}+fix"
    return out


def _explainer_shots(film: dict) -> dict:
    """Explainer shots in the common shot shape. The picture is drawn later by the authoring step (author_film)."""
    film["format"] = "explainer"
    film["style"] = ""
    for s in film["shots"]:
        s.update(kind="scene", image="", anim=NO_ANIM, framing="medium", move="push_in", overlay=NO_OVERLAY, transition="cut")
    return film


def _lesson_shots(film: dict) -> dict:
    """Lesson lines in the common shot shape; scenes numbered 0, 1, 2... in order whatever Claude wrote."""
    film["format"] = "lesson"
    film["style"] = ""
    film["subtitles"] = "en" if film.get("lang") == "en" else "ta"
    seen, last = {}, None
    for s in film["shots"]:
        first = s.get("scene") != last
        if first:
            last = s.get("scene")
            seen[len(seen)] = True
        s["scene"] = len(seen) - 1
        objs = []
        for o in (s.get("objects") or []) if first else []:  # the scene's real things, each a real 3D model
            slug = "-".join(re.findall(r"[a-z0-9]+", str(o.get("name", "")).lower()))[:40]
            if slug and slug not in [x["slug"] for x in objs]:
                objs.append({"slug": slug, "name": str(o["name"])[:60], "look": str(o.get("look", ""))[:400]})
        s.update(kind="scene", image="", objects=objs, anim=NO_ANIM, framing="medium", move="push_in",
                 overlay=NO_OVERLAY, transition="cut")
    # the intro lines go first, as scene -1: no props, the host in the centre with today's 3 points
    intro = film.pop("intro", None) or {}
    film["agenda"] = [{"ta": str(a.get("ta", "")).strip()[:48], "en": str(a.get("en", "")).strip()[:48]} for a in intro.get("agenda", [])][:3]
    film["shots"] = [{**{k: l.get(k) for k in ("ta", "en", "mood", "act")}, "scene": -1, "intro": True, "picture": "", "kind": "scene",
                      "image": "", "objects": [], "anim": NO_ANIM, "framing": "medium", "move": "push_in", "overlay": NO_OVERLAY,
                      "transition": "cut"} for l in intro.get("lines", [])] + film["shots"]
    seen_slugs, film["objects"] = set(), []
    for s in film["shots"]:
        for o in s["objects"]:
            if o["slug"] not in seen_slugs and len(film["objects"]) < 12:
                seen_slugs.add(o["slug"])
                film["objects"].append(o)
    return film


def _prompt(name: str, lang: str) -> str:
    """A writer's rules (film.md, explainer.md); an English video adds english.md on top."""
    return (PROMPTS / name).read_text() + ("\n\n" + (PROMPTS / "english.md").read_text() if lang == "en" else "")


def _lesson_prompt(lang: str) -> str:
    """The lesson writer's rules: Tamil narration, or English for an international series (lesson-en.md on top)."""
    return (PROMPTS / "lesson.md").read_text() + ("\n\n" + (PROMPTS / "lesson-en.md").read_text() if lang == "en" else "")


def write_film(plan: dict, previous: list[dict] | None = None) -> tuple[dict, dict]:
    prompt = f"Approved plan:\n{json.dumps(plan, ensure_ascii=False, indent=1)}\n\n"
    if plan.get("notes"):
        prompt += f"The owner's instructions (they win over the default rules): {plan['notes']}\n\n"
    if previous:  # earlier parts of this series: continue from them, do not repeat them
        prompt += ("Earlier parts of this series (already published; continue from where the last one ended, open with a "
                   "one-line reminder of it, do not repeat its facts, end by teasing what comes next only if more parts "
                   "make sense):\n" + "\n".join(f"- Part {r['part']}: \"{r['title']}\": {r['said'][:900]}" for r in previous) + "\n\n")
    prompt += _text_rule(plan.get("subtitles", "en")) + "Write the full shot list."
    if plan.get("format") == "lesson":
        film, usage = claude_json(_lesson_prompt(plan.get("lang", "ta")), prompt, LESSON_SCHEMA, "film")
        film["lang"] = plan.get("lang", "ta")  # the narration language: "en" = Kokoro voice, English captions and labels
        film = clean_film(_lesson_shots(film))
        film["brief"] = {k: plan.get(k, "") for k in ("topic", "angle", "audience", "notes", "category", "series", "part", "subtitles", "lang")}
    elif plan.get("format") == "explainer":
        film, usage = claude_json(_prompt("explainer.md", plan.get("lang", "ta")), prompt, EXPLAINER_SCHEMA, "film")
        film["lang"] = plan.get("lang", "ta")
        film = clean_film(_explainer_shots(film))
        film["brief"] = {k: plan.get(k, "") for k in ("topic", "angle", "audience", "notes", "category", "series", "part", "subtitles", "lang")}
    else:
        film, usage = claude_json(_prompt("film.md", plan.get("lang", "ta")), prompt, FILM_SCHEMA, "film")
        film["format"] = plan.get("format") or ("story" if film.get("for_kids") else "facts")
        film["lang"] = plan.get("lang", "ta")  # "en": English narration (Kokoro), English captions and words on screen
        film = clean_film(film)
    for k in ("category", "series", "part", "subtitles"):
        film[k] = plan.get(k, {"category": "education", "series": "", "part": 1, "subtitles": "en"}[k])
    return trend_tags(film), usage


NEWS_FEEDS = {  # free RSS, no key: world news from several outlets, so a story reported by many stands out
    "BBC": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "BBC Top": "https://feeds.bbci.co.uk/news/rss.xml",
    "BBC Science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "BBC Tech": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "NPR": "https://feeds.npr.org/1004/rss.xml",
    "The Guardian": "https://www.theguardian.com/world/rss",
    "DW": "https://rss.dw.com/rdf/rss-en-all",
    "Google News": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
}
NEWS_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["stories"],
    "properties": {"stories": {"type": "array", "minItems": 3, "maxItems": 3, "items": {
        "type": "object", "additionalProperties": False, "required": ["headline", "summary", "why", "items"],
        "properties": {"headline": {"type": "string"}, "summary": {"type": "string"}, "why": {"type": "string"},
                       "items": {"type": "array", "minItems": 1, "maxItems": 4, "items": {"type": "integer"}}}}}},
}


def _feed(name: str, url: str, hours: float = 36) -> list[dict]:
    """One RSS or RDF feed: its recent items as {source, title, text, link}; nothing if the feed fails."""
    import email.utils
    import html
    import xml.etree.ElementTree as ET
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (news reader)"})
        root = ET.fromstring(urllib.request.urlopen(req, timeout=20).read())
    except Exception:  # noqa: BLE001 - one feed down must not stop the others
        return []
    out, now = [], time.time()
    for it in [e for e in root.iter() if e.tag.split("}")[-1] == "item"][:30]:
        f = {c.tag.split("}")[-1]: (c.text or "").strip() for c in it}
        when = f.get("pubDate") or f.get("date") or ""
        try:
            age = now - (email.utils.parsedate_to_datetime(when).timestamp() if "," in when else
                         datetime.datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp())
        except (TypeError, ValueError):
            age = 0
        if age > hours * 3600 or not f.get("title"):
            continue
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", f.get("description", "")))).strip()
        out.append({"source": name, "title": html.unescape(f["title"]), "text": text[:280], "link": f.get("link", "")})
    return out


def latest_news(made: list[str]) -> tuple[list[dict], dict]:
    """Today's world headlines from free feeds; Claude picks the 3 best stories for a video, from those facts only."""
    with concurrent.futures.ThreadPoolExecutor(len(NEWS_FEEDS)) as ex:
        items = [x for got in ex.map(lambda kv: _feed(*kv), NEWS_FEEDS.items()) for x in got]
    seen, uniq = set(), []
    for x in items:
        k = re.sub(r"[^a-z0-9]", "", x["title"].lower())[:60]
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    if len(uniq) < 5:
        raise StepError("the news feeds did not answer; try again in a few minutes")
    uniq = uniq[:160]
    lines = "\n".join(f"{i}. [{x['source']}] {x['title']}" + (f" — {x['text']}" if x["text"] else "") for i, x in enumerate(uniq, 1))
    prompt = (f"Today's headlines:\n{lines}\n\nTopics the channel already made (do not repeat): "
              f"{'; '.join(made[-40:]) or 'none'}\n\nPick the 3 best stories.")
    d, usage = claude_json((PROMPTS / "news.md").read_text(), prompt, NEWS_SCHEMA, "news")
    stories = []
    for s in d["stories"][:3]:
        src = [uniq[i - 1] for i in s["items"] if 1 <= i <= len(uniq)]
        stories.append({"headline": s["headline"].strip()[:80], "summary": s["summary"].strip()[:1200], "why": s["why"].strip()[:300],
                        "sources": [{"name": x["source"], "title": x["title"][:200], "link": x["link"][:400]} for x in src]})
    return stories, usage


def _text_rule(subtitles: str) -> str:
    """Tells the script writer which language every on-screen word is in (hook, overlays, graphic titles and labels)."""
    return ("\nOn-screen words (the hook, thumbnail words, overlay text and captions, animated graphic titles and labels) must be in Tamil "
            "script, short and simple; this replaces the 'English' wording of those fields.\n" if subtitles == "ta" else "")


EDIT_INTENT_SCHEMA = {"type": "object", "additionalProperties": False,
                      "required": ["format", "subtitles", "lang", "voice_start", "gap", "music"],
                      "properties": {"format": {"enum": FORMATS}, "subtitles": {"enum": ["ta", "en"]}, "lang": {"enum": ["ta", "en"]},
                                     "voice_start": {"type": "number"}, "gap": {"type": "number"},
                                     "music": {"enum": list(MUSIC_LEVEL)}}}
EDIT_INTENT = """A video exists in one of three formats:
- "explainer": drawn, illustrated motion graphics (cartoon-like drawn people and objects), no photos.
- "facts": AI-generated pictures (realistic images/photos) with camera moves and a few animated graphics and text.
- "story": storybook pictures for a children's story.
Its on-screen text (subtitles and words on screen) is in "ta" (Tamil script) or "en" (English).
The owner watched it and wrote a change request. Return the format and on-screen text language the video should
have AFTER the change. Keep the current value unless the owner asks for something that needs the other: asking for
images, pictures, photos or realistic visuals instead of drawings or characters means "facts" (or "story" for a
kids story); asking for drawn, cartoon or fully animated instead of pictures means "explainer"; asking for Tamil
or English text switches the language. Animated text over pictures is still "facts".
Its voice (the narration) is spoken in "ta" (Tamil) or "en" (English): return it as lang. Keep the current value unless
the owner asks for the voice, narration or audio in the other language ("english voice", "speak in Tamil"). The text
language and the voice language are separate: change only the one the owner names.
It also has three sound settings: voice_start (seconds of picture and music before the first spoken word; the
on-screen text of a line appears with its voice), gap (seconds of quiet between two spoken lines) and music
("on", "soft" = quieter, "off" = none). Return them as they should be AFTER the change: keep the current value
unless the owner asks about when the voice or text starts, the pauses between lines, or the background music.
"Start the voice 2 or 3 seconds after the video starts" means voice_start 2.5."""


def edit_intent(film: dict, change: str) -> tuple[str, str, dict, str]:
    """Which format, on-screen language, sound settings and voice language the owner's re-edit asks for (their words, read by the model)."""
    cur = (film.get("format", "facts"), film.get("subtitles", "en"))
    lang = film.get("lang") or "ta"
    old, now = film.get("sound") or {}, sound_of(film)
    try:
        d, _ = claude_json(EDIT_INTENT, f"Current format: {cur[0]}. Current on-screen text: {cur[1]}. Current voice: {lang}. For kids: {bool(film.get('for_kids'))}.\n"
                           f"Current sound settings: voice_start {now['voice_start']}, gap {now['gap']}, music {now['music']}.\n"
                           f"Change request:\n\"\"\"\n{change}\n\"\"\"", EDIT_INTENT_SCHEMA, "edit-intent", "haiku", think=False)
        want = sound_of({"format": film.get("format"), "sound": d})
        # keep only what an edit set, so a film that changes format still gets the new format's own defaults
        return d["format"], d["subtitles"], {k: want[k] for k in now if k in old or want[k] != now[k]}, d["lang"]
    except (StepError, KeyError, TypeError, ValueError):
        return (*cur, old, lang)


def _lang_rule(old: str, new: str) -> str:
    """Tells the script writer that the edit changes the spoken language."""
    name = {"ta": "Tamil", "en": "English"}
    return (f"\nThe narration changes from {name[old]} to {name[new]}: follow the {name[new]} rules above for every field "
            "(spoken lines, title, description, hashtags, tags), and keep what each line says.\n" if old != new else "")


SOUND_RULE = ("\nWhen the voice starts, the pauses between lines and the background music are set separately: never change, "
              "add or remove a line for a request about those.")


def revise_film(film: dict, change: str) -> tuple[dict, dict]:
    if film.get("format") == "lesson":
        view = {k: v for k, v in film.items() if k not in ("shots", "agenda")}
        view["intro"] = {"lines": [{k: s[k] for k in ("ta", "en", "mood", "act")} for s in film["shots"] if s.get("intro")],
                         "agenda": film.get("agenda", [])}
        view["shots"] = [s for s in film["shots"] if not s.get("intro")]
        prompt = (f"Current lesson:\n{json.dumps(view, ensure_ascii=False, indent=1)}\n\nThe owner watched the video and asks for "
                  f"this change:\n{change}\n\nReturn the full revised lesson. Keep every line the change does not touch exactly as "
                  "it is, word for word, so its voice can be reused. If the change is only about how it looks or moves, return "
                  "every line unchanged: the motion designer gets the owner's words too." + SOUND_RULE)
        _, _, sound, lang = edit_intent(film, change)
        film2, usage = claude_json(_lesson_prompt(lang), prompt + _lang_rule(film.get("lang") or "ta", lang), LESSON_SCHEMA, "film-edit")
        film2["lang"] = lang
        film2 = clean_film(_lesson_shots(film2))
        for k in ("category", "series", "part", "brief"):  # subtitles follow the voice language (_lesson_shots)
            if k in film:
                film2[k] = film[k]
        film2["author_change"] = change
        film2["sound"] = sound
        if film2.get("brief"):
            film2["brief"]["lang"] = lang
        return trend_tags(film2), usage
    fmt, subs, sound, lang = edit_intent(film, change)
    if lang == "en":
        subs = "en"  # an English video has English words on screen
    relang = _lang_rule(film.get("lang") or "ta", lang)
    switched = fmt != film.get("format", "facts")
    lines = [{k: sh.get(k, "") for k in ("ta", "en", "mood")} for sh in film["shots"]]
    prompt = (f"Current shot list:\n{json.dumps(lines if switched else film, ensure_ascii=False, indent=1)}\n\n"
              f"The owner watched the video and asks for this change:\n{change}\n\n"
              + ("The film is being remade in this format, so write every field the schema asks for; keep the narration lines "
                 "(ta, en) unless the change asks to change them." if switched else
                 "Return the full revised shot list. Keep every shot that the change does not touch exactly as it is, "
                 "word for word, so its picture and voice can be reused.") + SOUND_RULE)
    if fmt == "explainer":
        film2, usage = claude_json(_prompt("explainer.md", lang), prompt + relang + (
            "\nIf the change is only about how the film looks or moves (drawings, colours, animation, pacing of the "
            "picture), return every line unchanged: the illustrator gets the owner's words too."), EXPLAINER_SCHEMA, "film-edit")
        film2["lang"] = lang
        film2 = clean_film(_explainer_shots(film2))
        film2["brief"] = film.get("brief", {})
        film2["author_change"] = change  # the illustrator applies it to the drawn scenes
    else:
        film2, usage = claude_json(_prompt("film.md", lang), prompt + relang + _text_rule(subs), FILM_SCHEMA, "film-edit")
        film2["format"] = fmt
        film2["lang"] = lang
        film2 = clean_film(film2)
    for k in ("category", "series", "part", "subtitles"):
        if k in film:
            film2[k] = film[k]
    film2["subtitles"] = subs
    film2["sound"] = sound
    if film2.get("brief"):
        film2["brief"]["subtitles"] = film2.get("subtitles", "en")
        film2["brief"]["lang"] = lang
    return trend_tags(film2), usage


LETTERS = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "ஏ பி சி டி ஈ எஃப் ஜி ஹெச் ஐ ஜே கே எல் எம் என் ஓ பி க்யூ ஆர் எஸ் டி யூ வி டபிள்யூ எக்ஸ் வை இசட்".split()))


def speakable(ta: str) -> str:
    """The narration as the voice can read it: English letters (AI, DNA) become their Tamil letter names with spaces
    (ஏ ஐ), and hyphens, brackets, quotes and emoji go. The prompt asks for this; this catches what slips through."""
    ta = re.sub(r"[A-Za-z]+", lambda m: " " + " ".join(LETTERS[c] for c in m.group(0).upper()) + " ", ta)
    ta = re.sub(r"[-–—_()\[\]{}\"“”‘’*#/\\|<>]+|[\U0001F000-\U0001FAFF\u2600-\u27BF]", " ", ta)
    return re.sub(r"\s+([,.!?…])", r"\1", re.sub(r"\s{2,}", " ", ta)).strip()


def clean_film(film: dict) -> dict:
    """Guard the engine against small slips in Claude's JSON."""
    tags = [h if h.startswith("#") else f"#{h}" for h in film.get("hashtags", [])]
    musts = ["#shorts", "#kidsstory", "#storiesforkids", "#knowthisdaily"] if film.get("for_kids") else \
        ["#shorts", "#tamil", "#knowthisdaily"]
    if film.get("format") == "lesson":  # a normal 16:9 video: never tagged as a Short
        musts = [m for m in musts if m != "#shorts"]
        tags = [t for t in tags if t.lower() != "#shorts"]
    if film.get("lang") == "en":  # an English video for the world: no Tamil tag
        musts = [m for m in musts if m != "#tamil"]
        tags = [t for t in tags if "tamil" not in t.lower()]
    tags = musts + [t for t in tags if t.lower() not in musts]  # musts first, so the cap never drops them
    film["hashtags"] = list(dict.fromkeys(re.sub(r"\s+", "", t) for t in tags))[:12 if film.get("lang") == "en" else 6]
    en = [h if h.startswith("#") else f"#{h}" for h in film.get("en_hashtags", [])]
    en_musts = ["#shorts", "#kidsstory", "#storiesforkids", "#knowthisdaily"] if film.get("for_kids") else \
        ["#shorts", "#facts", "#knowthisdaily"]
    if film.get("format") == "lesson":
        en_musts = [m for m in en_musts if m != "#shorts"]
        en = [h for h in en if h.lower() != "#shorts"]
    en = en_musts + [h for h in en if h.lower() not in en_musts and "tamil" not in h.lower()]
    film["en_hashtags"] = [re.sub(r"\s+", "", h) for h in en][:12]
    film["en_title"] = (film.get("en_title") or film["title"].split("|")[-1]).strip()[:100]
    film["en_description"] = (film.get("en_description") or "").strip()
    film["title"] = film["title"].strip()[:100]
    film["hook"] = " ".join(film["hook"].split()[:7]) or "Know this"
    t = film.get("thumb") if isinstance(film.get("thumb"), dict) else {}  # an older film has none: the hook stands in
    film["thumb"] = {"words": " ".join(str(t.get("words") or film["hook"]).split()[:5]),
                     "line": " ".join(str(t.get("line") or "").split()[:8]),
                     "shot": min(max(int(t.get("shot") or 0), 0), len(film["shots"]) - 1)}
    none = {"kind": "none", "text": "", "value": 0, "suffix": ""}
    for s in film["shots"]:
        s["ta"] = speakable(s["ta"])
    for i, s in enumerate(film["shots"]):
        if s.get("kind") == "scene" or film.get("format") == "lesson":  # programmed scenes stay; only the subtitle highlight is tidied
            s["en"] = re.sub(r"\*([^*]*\s[^*]*)\*", r"\1", s["en"])
            continue
        a = s.get("anim") or {}
        has_anim = a.get("type") in ANIMS and (a.get("items") or a.get("type") in ("wave", "globe"))
        if i == 0 or not has_anim:
            s["kind"] = "photo"  # the hook is always a picture; an empty scene falls back to one
        if s["kind"] == "photo" and not s.get("image", "").strip():
            s["image"] = s["en"].replace("*", "")
        if s["kind"] == "anim" or i == 0:
            s["overlay"] = none  # the scene or the hook already fills the frame
        s["en"] = re.sub(r"\*([^*]*\s[^*]*)\*", r"\1", s["en"])  # drop multi-word highlights
    return film


# ---------------------------------------------------------------- trending tags

# What people really type into YouTube search: its free suggestion service, most searched first.
SUGGEST = "https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&hl=en&q="
OTHER_LANGS = re.compile(r"\b(hindi|malayalam|kannada|telugu|marathi|gujarati|bengali|urdu|odia|punjabi|adults?|18)\b", re.I)
TAG_WORDS = set("for kids kid children child tamil story stories bedtime moral cartoon cartoons animation animated short shorts "
                "baby toddlers toddler cute funny 3d fairy tale tales the in with little brave new time storytime magic "
                "magical jungle animal animals forest ocean space adventure good night lullaby facts fact explained "
                "science history how why what amazing interesting world biggest secret mystery mysteries video videos".split())
KIDS_SEEDS = ["kids story", "bedtime stories", "moral stories", "tamil story", "cartoon story"]


def suggest(query: str) -> list[str]:
    req = urllib.request.Request(SUGGEST + urllib.parse.quote(query), headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return [s for s in json.loads(r.read().decode("utf-8", "replace"))[1] if isinstance(s, str)]
    except Exception:
        return []


def trend_tags(film: dict) -> dict:
    """Mix today's most searched YouTube phrases into the tags and hashtags. Claude's own tags stay as the fallback."""
    seeds = (KIDS_SEEDS if film.get("for_kids") else []) + [s for s in film.get("tags", [])[:3] if s.isascii()]
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        found = [s for hits in ex.map(suggest, seeds) for s in hits[:4]]
    # Keep a phrase only if every word it adds to its seed is a plain kids/story word: no names, numbers or podcasts.
    words = {w for s in seeds for w in s.lower().split()}
    found = [s.lower().strip() for s in found if not OTHER_LANGS.search(s)
             and all(w in words or w in TAG_WORDS for w in s.lower().split())]
    found = list(dict.fromkeys(found))  # may be empty: the hashtag order below still applies
    # YouTube tags: searched phrases first, then Claude's; YouTube allows 500 characters in all.
    tags, size = [], 0
    for s in found + film.get("tags", []):
        if s.lower() not in (x.lower() for x in tags) and size + len(s) + 3 <= 480:
            tags.append(s)
            size += len(s) + 3
    film["tags"] = tags
    # Hashtags: the fixed ones, Claude's specific topic tags, then one searched phrase if room; 6 at most (a few
    # precise tags beat many broad ones).
    musts = [h for h in film["hashtags"] if h.lower() in ("#shorts", "#kidsstory", "#storiesforkids", "#knowthisdaily", "#tamil")]
    searched = ["#" + re.sub(r"[^a-z0-9]", "", s) for s in found if len(s.split()) <= 3]
    rest = [h for h in film["hashtags"] if h not in musts]
    out = []
    # English lessons reach the whole world: the 3 broadest topic tags first (YouTube shows those above the title),
    # more searched phrases, the channel tag last; 12 in all (YouTube ignores every hashtag past 15).
    order = rest + searched[:5] + musts if film.get("lang") == "en" else musts + rest + searched[:1]
    for h in order:
        if len(h) > 2 and h.lower() not in (x.lower() for x in out):
            out.append(h)
    film["hashtags"] = out[:12] if film.get("lang") == "en" else out[:6]
    en_out = []
    for h in film.get("en_hashtags", [])[:3] + [x for x in searched[:6] if "tamil" not in x] + film.get("en_hashtags", [])[3:]:
        if len(h) > 2 and h.lower() not in (x.lower() for x in en_out):
            en_out.append(h)
    film["en_hashtags"] = en_out[:12]
    if found:
        film["tag_source"] = "youtube search"
    return film


# ---------------------------------------------------------------- pictures

def _hf_token() -> str | None:
    p = CONFIG / "hf-token"
    return p.read_text().strip() if p.exists() else None


def _gradio_image(space: str, prompt: str, seed: int, signed_in: bool) -> str:
    from gradio_client import Client  # imported here: only needed on the machine that makes pictures

    c = Client(space, token=_hf_token() if signed_in else None, verbose=False)
    if "Z-Image" in space:
        res = c.predict(prompt=prompt, resolution="1152x2048 ( 9:16 )", seed=seed, random_seed=False, api_name="/generate")
    else:
        res = c.predict(prompt=prompt, seed=seed, randomize_seed=False, width=1088, height=1920,
                        num_inference_steps=4, api_name="/infer")
    img = res[0] if isinstance(res, (list, tuple)) else res
    while isinstance(img, list):
        img = img[0]
    if isinstance(img, dict):
        img = img.get("image") or img.get("path") or img
    if isinstance(img, dict):
        img = img.get("path")
    return img


_poll_lock = threading.Lock()
_poll_last = [0.0]
POLL_GAP = 47  # Pollinations' free tier: one picture every 45 seconds per IP address


def _pollinations(prompt: str, seed: int, dest: Path) -> str:
    url = (f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt, safe='')}"
           f"?width=1088&height=2048&nologo=true&seed={seed}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with _poll_lock:  # one at a time, spaced out, across all threads
        for attempt in range(3):
            time.sleep(max(0.0, _poll_last[0] + POLL_GAP - time.monotonic()))
            _poll_last[0] = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = r.read()
                break
            except urllib.error.HTTPError as e:
                if e.code != 402 or attempt == 2:
                    raise
    if data[:2] != b"\xff\xd8" and data[:4] != b"\x89PNG":
        raise StepError("pollinations returned no picture")
    raw = dest.with_suffix(".raw")
    raw.write_bytes(data)
    return str(raw)


# Picture sources in order. The free GPU keeps one daily quota per account and one per machine (guest). The
# account's quota is kept for Kayal's voice (the only voice the owner accepts), so pictures use the guest quota
# and Pollinations first and the account only as a last resort.
SOURCES = [("Tongyi-MAI/Z-Image-Turbo", False), ("black-forest-labs/FLUX.1-schnell", False), ("pollinations", False),
           ("Tongyi-MAI/Z-Image-Turbo", True), ("black-forest-labs/FLUX.1-schnell", True)]
QUOTA = re.compile(r"quota|exceeded|rate limit|too many", re.I)


def picture(prompt: str, seed: int, dest: Path, spent: set) -> str:
    """One 1152x2048 picture from the best source that still has free quota (`spent` is shared per run)."""
    errors = []
    for space, signed_in in SOURCES:
        name = space.split("/")[-1] + ("" if signed_in or space == "pollinations" else " (guest)")
        if name in spent or (signed_in and not _hf_token()):
            continue
        for attempt in range(2):
            try:
                if space == "pollinations":
                    src = _pollinations(prompt, seed, dest)
                else:
                    src = _gradio_image(space, prompt, seed, signed_in)
                crop = "crop=iw:ih*0.955:0:0," if space == "pollinations" else ""  # its watermark sits in the bottom strip
                run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf",
                     f"{crop}scale=1152:2048:force_original_aspect_ratio=increase:flags=lanczos,crop=1152:2048,"
                     "eq=contrast=1.05:saturation=1.08,unsharp=5:5:0.35", "-q:v", "3", str(dest)], "picture")
                return name
            except Exception as e:
                errors.append(f"{name}: {str(e)[:140]}")
                if QUOTA.search(str(e)):
                    spent.add(name)  # no point asking again today
                    break
                time.sleep(4 * (attempt + 1))
    raise StepError("no picture from any source: " + " | ".join(errors[-4:]))


def pictures(film: dict, assets: Path, cache: Path) -> dict:
    """A picture per shot, reused from the cache when the prompt did not change."""
    cache.mkdir(parents=True, exist_ok=True)
    used: dict[str, int] = {}
    spent: set = set()

    def one(i_shot):
        i, s = i_shot
        if s.get("kind") in ("anim", "scene"):
            return "animated"
        prompt = f"{s['image']}. {film['style']}. vertical 9:16 composition, no text, no watermark"
        key = hashlib.sha1(prompt.encode()).hexdigest()[:16]
        cached = cache / f"{key}.jpg"
        source = "cache"
        if not cached.exists():
            tmp = cache / f"{key}.part.jpg"
            source = picture(prompt, 1000 + i * 97, tmp, spent)
            tmp.replace(cached)
        shutil.copy(cached, assets / f"shot-{i}.jpg")
        return source

    # Two at a time: the free GPU queues more, and one at a time is twice as slow.
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        for src in pool.map(one, enumerate(film["shots"])):
            used[src] = used.get(src, 0) + 1
    return used


# ---------------------------------------------------------------- voice

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # a redirect here means the key was refused
        return None


def _box_audio(path: str, body: dict, timeout: int = 60) -> bytes | None:
    """Audio from the TTS box (its private port), or None when it is not set up, not answering or failed."""
    f = CONFIG / "tts.json"
    if not f.exists():
        return None
    cfg = json.loads(f.read_text())
    req = urllib.request.Request(
        f"{cfg['url']}{path}", method="POST", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg['token']}"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
            data = r.read()
        return data if r.status == 200 and len(data) > 1000 else None
    except Exception:
        return None


def _box_call(method: str, path: str, body: dict | None = None, timeout: int = 30) -> tuple[int, bytes]:
    """(HTTP status, body) from the TTS box; status 0 when it is not set up or not reachable."""
    f = CONFIG / "tts.json"
    if not f.exists():
        return 0, b""
    cfg = json.loads(f.read_text())
    req = urllib.request.Request(
        f"{cfg['url']}{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg['token']}"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception:
        return 0, b""


def _tts_box(text: str, voice: str, rate: str, pitch: str) -> bytes | None:
    return _box_audio("/tts", {"text": text, "voice": voice, "rate": rate, "pitch": pitch})


async def _speak(text: str, voice: str, mood: str, mp3: Path) -> None:
    rate, pitch = PROSODY.get(mood, ("+0%", "+0Hz"))
    # The TTS box first, so this machine's CPU stays on pictures and rendering; edge-tts here if it fails.
    data = await asyncio.to_thread(_tts_box, text, voice, rate, pitch)
    if data:
        mp3.write_bytes(data)
        return
    import edge_tts

    for attempt in range(3):
        with mp3.open("wb") as f:
            async for chunk in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
        if mp3.stat().st_size > 1000:
            return
        await asyncio.sleep(2 * (attempt + 1))  # edge-tts gives an empty stream when Microsoft rejects a request
    raise StepError(f"no voice for: {text[:60]}")


INDIC = "indicf5"  # the channel narrator: IndicF5 on CPU, on the TTS box and on this box at the same time
INDIC_VOICE = os.environ.get("SHORTS_INDIC_VOICE", "rasa-book-0.80")  # sample G, the owner's pick 2026-11-17  # = VOICE_VERSION in tts_server.py: new pace, new lines
LOCAL_INDIC = os.environ.get("SHORTS_LOCAL_INDIC", "http://127.0.0.1:8082")  # indic-local.service on this box
INDIC_WAIT = 75 * 60   # give up after this (both boxes resting for long); Try again reuses finished lines
PER_WORKER = 2         # lines handed to each box at once: one being made, one waiting, so neither idles
WORKER_GRACE = 180     # seconds a box may stay silent before its lines move to the other box


def _local_call(method: str, path: str, body: dict | None = None, timeout: int = 30) -> tuple[int, bytes]:
    """(HTTP status, body) from the IndicF5 worker on this box; status 0 when it is not running."""
    req = urllib.request.Request(LOCAL_INDIC + path, method=method, headers={"Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception:
        return 0, b""


def _indic_all(todo: list[tuple[dict, Path]]) -> bool:
    """Every line from IndicF5, shared between the TTS box and this box.

    Each box gets the next line as soon as it has room, so both stay busy. Requests stay short (the instabox port
    proxy cuts requests after about 20 s): lines are queued, then polled. A box that fails a line or goes silent
    (resting, restarting, down) has its lines moved to the other box. False if the lines cannot all be made."""
    workers = {"tts box": _box_call, "video box": _local_call}
    waiting = list(todo)
    held: dict[str, dict[Path, tuple[str, dict]]] = {w: {} for w in workers}
    seen = {w: time.monotonic() for w in workers}
    resting = {w: 0.0 for w in workers}
    fails: dict[Path, int] = {}
    deadline = time.monotonic() + INDIC_WAIT

    def submit(w: str, s: dict) -> str | None:
        rate = PROSODY.get(s["mood"], ("+0%", "+0Hz"))[0]
        code, body = workers[w]("POST", "/indic/jobs", {"text": s["ta"], "rate": rate})
        if code == 200:
            seen[w] = time.monotonic()
            return json.loads(body)["id"]
        return None

    while (waiting or any(held.values())) and time.monotonic() < deadline:
        if should_stop():
            raise Cancelled("cancelled")
        now = time.monotonic()
        for w, call in workers.items():
            for f, (jid, s) in list(held[w].items()):
                if f.exists():  # the other box already made it
                    del held[w][f]
                    continue
                code, body = call("GET", f"/indic/jobs/{jid}")
                if code in (200, 202, 404, 500):
                    seen[w] = now
                if code == 200 and len(body) > 1000:
                    tmp = f.with_suffix(f".{w[:3]}.part.mp3")
                    tmp.write_bytes(body)
                    tmp.replace(f)
                    del held[w][f]
                elif code == 404:  # the worker restarted and forgot the line
                    del held[w][f]
                    waiting.insert(0, (s, f))
                elif code == 500:  # failed there: try the other box, at most 3 times in all
                    del held[w][f]
                    fails[f] = fails.get(f, 0) + 1
                    if fails[f] >= 3:
                        return False
                    waiting.insert(0, (s, f))
                    resting[w] = now + 60
            if held[w] and now - seen[w] > WORKER_GRACE:
                waiting[:0] = [(s, f) for f, (_, s) in held[w].items()]
                held[w].clear()
                resting[w] = now + 120
        for w in workers:
            while waiting and len(held[w]) < PER_WORKER and resting[w] <= now:
                s, f = waiting[0]
                if f.exists():
                    waiting.pop(0)
                    continue
                jid = submit(w, s)
                if not jid:
                    resting[w] = now + 60
                    break
                waiting.pop(0)
                held[w][f] = (jid, s)
        if waiting or any(held.values()):
            time.sleep(5)
    return not waiting and not any(held.values())


MAYA = "maya2"  # the channel narrator the owner chose: Maya 2 Native on the owner's private ZeroGPU Space
MAYA_SPACE = os.environ.get("SHORTS_VOICE_SPACE", "")  # the narrator voice Space, from the SHORTS_VOICE_SPACE secret
MAYA_VOICES = {"female": "Kayal", "male": "Abhay"}
TRIM = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB,areverse,loudnorm=I=-16:TP=-1.5")
voice_gpu_done = threading.Event()  # set once the voice has had its turn on the free GPU; pictures wait for it
voice_gpu_done.set()


def _maya_all(todo: list[tuple[dict, Path]], voice: str) -> bool:
    """Every missing line in ONE request to the voice Space (one GPU booking per video; the free tier allows about
    5 GPU minutes a day). False when the Space or the day's quota is not available: the box voice takes over."""
    if not todo:
        return True
    token = _hf_token()
    if not (token and MAYA_SPACE):
        return False
    try:
        from gradio_client import Client

        res = Client(MAYA_SPACE, token=token, verbose=False).predict(
            lines=[s["ta"] for s, _ in todo], lang="ta", voice=voice, seed=7, api_name="/lines")
        audio = res["audio"]
        if len(audio) != len(todo):
            raise ValueError(f"{len(audio)} lines back for {len(todo)}")
        with tempfile.TemporaryDirectory() as tmp:
            for i, ((_, f), b64) in enumerate(zip(todo, audio)):
                raw = Path(tmp) / f"{i}.flac"
                raw.write_bytes(base64.b64decode(b64))
                part = f.with_suffix(".part.mp3")
                run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af", TRIM, "-ar", "24000", "-ac", "1",
                     "-b:a", "96k", str(part)], "voice")
                part.replace(f)
        return True
    except Exception as e:  # noqa: BLE001 - quota used up, Space asleep or down: never lose the film over it
        global maya_error
        maya_error = str(e)[:300]
        print(f"Maya voice not available: {maya_error}")
        return False


maya_error = ""


def _maya_why() -> str:
    """The Space's refusal in the owner's words."""
    m = re.search(r"Try again in (\d+):(\d+)", maya_error)
    if "quota" in maya_error.lower():
        wait = f" It comes back in about {int(m.group(1))} h {int(m.group(2))} min." if m else " It comes back within a day."
        return "Kayal's voice could not be made: today's free GPU time is used up." + wait + " Then tap Try again."
    return "Kayal's voice could not be made (the voice Space is waking up or down). Tap Try again in a few minutes."


def voices(film: dict, work: Path, cache: Path) -> tuple[list[float], str]:
    """One voice file per shot (cached by engine and text). Returns each line's length and the engine used.

    One narrator for the whole film: Maya 2 (voice Kayal, the owner's choice) on the private GPU Space. The owner
    rejected the IndicF5 voice for published films, so when Kayal is not available the film stops with Try again
    instead of using it. SHORTS_BACKUP_VOICE=1 allows IndicF5 again; SHORTS_EDGE_FALLBACK=1 also allows edge-tts."""
    cache.mkdir(parents=True, exist_ok=True)
    edge = VOICES.get(film["voice"], VOICES["female"])
    maya_voice = MAYA_VOICES["female"]  # the owner wants Kayal on every film, whatever narrator the script suggests
    engines = (MAYA,) + ((INDIC,) if os.environ.get("SHORTS_BACKUP_VOICE") == "1" else ()) \
        + ((edge,) if os.environ.get("SHORTS_EDGE_FALLBACK") == "1" else ())
    for engine in engines:
        key = f"{MAYA}|{maya_voice}" if engine == MAYA else f"{engine}|{INDIC_VOICE}"
        files = [cache / (hashlib.sha1(f"{key}|{'' if engine == MAYA else s['mood']}|{s['ta']}".encode()).hexdigest()[:16] + ".mp3")
                 for s in film["shots"]]
        todo = [(s, f) for s, f in zip(film["shots"], files) if not f.exists()]
        if engine == MAYA:
            ok = _maya_all(todo, maya_voice)
            voice_gpu_done.set()
            if ok:
                break
            continue
        if engine == INDIC:
            if _indic_all(todo):
                break
            continue

        async def all_lines():
            sem = asyncio.Semaphore(4)

            async def one(s, f):
                async with sem:
                    tmp = f.with_suffix(".part.mp3")
                    await _speak(s["ta"], engine, s["mood"], tmp)
                    tmp.replace(f)

            await asyncio.gather(*(one(s, f) for s, f in todo))

        asyncio.run(all_lines())
        break
    else:
        raise StepError(_maya_why() + " The pictures already made are kept.")
    for i, f in enumerate(files):
        shutil.copy(f, work / f"line-{i}.mp3")
    return [probe(f) for f in files], (f"Maya2 {maya_voice}" if engine == MAYA else ("Maya 2 Kayal (CPU)" if INDIC_VOICE.startswith("kayal") else "IndicF5 G (Rasa storytelling)") if engine == INDIC else "edge-tts")


# ---------------------------------------------------------------- English version

KOKORO = Path(os.environ.get("SHORTS_KOKORO", Path.home() / "kokoro"))  # Kokoro-82M (Apache-2.0) via kokoro-onnx (MIT)
EN_VOICES = {"female": "af_heart", "male": "am_michael"}
EN_PACE = 0.92  # the owner approved the 8% slower sample (samples/speed/5-english-8pct-slower.mp3)
EN_SPEED = {"excited": 1.08, "happy": 1.05, "tense": 1.05, "curious": 1.0, "dramatic": 0.98, "epic": 0.98,
            "calm": 0.95, "mysterious": 0.95, "sad": 0.92}
_kokoro = None
_kokoro_lock = threading.Lock()


def english_voices(film: dict, work: Path, cache: Path) -> list[float]:
    """English narration from Kokoro on this box's CPU: the subtitle text, spoken. A few seconds per line."""
    global _kokoro
    cache.mkdir(parents=True, exist_ok=True)
    voice = EN_VOICES.get(film["voice"], EN_VOICES["female"])
    files = []
    for s in film["shots"]:
        text = s["en"].replace("*", "").strip()
        f = cache / (hashlib.sha1(f"kokoro|{EN_PACE}|{voice}|{s['mood']}|{text}".encode()).hexdigest()[:16] + ".mp3")
        if not f.exists():
            import soundfile as sf

            with _kokoro_lock:
                if _kokoro is None:
                    from kokoro_onnx import Kokoro

                    _kokoro = Kokoro(str(KOKORO / "kokoro-v1.0.onnx"), str(KOKORO / "voices-v1.0.bin"))
                samples, rate = _kokoro.create(text, voice=voice, speed=EN_PACE * EN_SPEED.get(s["mood"], 1.0), lang="en-us")
            with tempfile.TemporaryDirectory() as tmp:
                wav = Path(tmp) / "a.wav"
                sf.write(wav, samples, rate)
                part = f.with_suffix(".part.mp3")
                run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af",
                     "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                     "silenceremove=start_periods=1:start_threshold=-45dB,areverse,loudnorm=I=-16:TP=-1.5",
                     "-ar", "24000", "-ac", "1", "-b:a", "96k", str(part)], "english voice")
                part.replace(f)
        files.append(f)
    for i, f in enumerate(files):
        shutil.copy(f, work / f"line-{i}.mp3")
    return [probe(f) for f in files]


def make_english(film: dict, job: Path, log=print) -> dict:
    """The same film narrated in English: same pictures and graphics, Kokoro voice -> job/video_en.mp4."""
    work, work_en = job / "work", job / "work-en"
    if work_en.exists():
        shutil.rmtree(work_en)
    work_en.mkdir(parents=True)
    for f in work.glob("shot-*.jpg"):
        shutil.copy(f, work_en / f.name)
    t = time.monotonic()
    log("english voice")
    lengths = english_voices(film, work_en, job.parent.parent / "cache" / "voice")
    film = {**film, "subtitles": "en"}
    plan_t = timeline(film, lengths)
    log("english render")
    if film.get("format") == "explainer":  # the scenes read their beats from timing.json: rebuild them on the English clock
        pen = job / "project-en"
        if pen.exists():
            shutil.rmtree(pen)
        shutil.copytree(job / "project", pen, ignore=shutil.ignore_patterns("snaps", ".hyperframes", "compositions", "node_modules"))
        (pen / "timing.json").write_text(json.dumps(author_clock(film, plan_t), ensure_ascii=False, indent=1))
        mix_audio(film, plan_t, work_en, pen / "assets" / "voice.mp3")
        errors = _author_errors(pen)
        if errors:
            raise StepError("the English film has errors:\n" + errors[-700:])
    else:
        assemble({**film, "title": film.get("en_title") or film["title"]}, plan_t, lengths, work_en, job / "project-en")
    tmp = job / "video_en.part.mp4"
    seconds = render(job / "project-en", tmp)
    tmp.replace(job / "video_en.mp4")
    preview(job / "video_en.mp4", job / "preview_en.mp4", seconds)
    return {"seconds_en": round(seconds, 1), "build_minutes_en": round((time.monotonic() - t) / 60, 1)}


# ---------------------------------------------------------------- timing and assembly

def split_words(text: str, limit: int = 6) -> list[str]:
    words = text.split()
    n = max(1, round(len(words) / limit + 0.49))
    size = -(-len(words) // n)
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def timeline(film: dict, lengths: list[float]) -> dict:
    """Where every shot, cut, line and subtitle sits in time."""
    # After a line: `hold` seconds on the finished picture, the cut, then `pre` seconds before the next line starts.
    # An explainer holds longer, so the viewer can take in the finished drawing before the voice moves on.
    snd = sound_of(film)
    pre = min(0.45, snd["gap"] / 2)
    hold = snd["gap"] - pre
    shots, subs, t = [], [], snd["voice_start"]
    for i, (s, d) in enumerate(zip(film["shots"], lengths)):
        v0, v1 = t, t + d
        start = 0.0 if i == 0 else round(v0 - pre, 3)
        shots.append({**{k: s[k] for k in ("kind", "anim", "move", "framing", "transition", "mood", "overlay")},
                      "scene": s.get("scene"), "en": s["en"],
                      "start": start, "voiceStart": round(v0, 3), "voiceEnd": round(v1, 3)})
        chunks = split_words(s["ta"], 4) if film.get("subtitles") == "ta" else split_words(s["en"])
        total = sum(len(c) for c in chunks)
        c0 = v0
        for j, c in enumerate(chunks):
            c1 = v1 if j == len(chunks) - 1 else c0 + d * len(c) / total
            subs.append({"text": c, "start": round(c0, 3), "end": round(c1, 3)})
            c0 = c1
        t = v1 + hold + pre
    end_start = round(shots[-1]["voiceEnd"] + max(END_HOLD, hold), 3)
    duration = round(end_start + END_CARD, 3)
    for i, s in enumerate(shots):
        s["end"] = shots[i + 1]["start"] if i + 1 < len(shots) else duration
        s["clipStart"] = 0.0 if i == 0 else round(max(0.0, s["start"] - PRE.get(s["transition"], 0.0)), 3)
        s["clipEnd"] = duration if i + 1 == len(shots) else round(s["end"] + 0.06, 3)
    # Each subtitle stays up until the next one, but never past the next line's start.
    for j, c in enumerate(subs):
        nxt = subs[j + 1]["start"] if j + 1 < len(subs) else end_start
        c["end"] = round(min(max(c["end"] + 0.25, c["end"]), nxt - 0.02), 3)
    return {"duration": duration, "endStart": end_start, "hook": "" if film.get("format") == "explainer" else film["hook"],  # an explainer draws its own hook in shot 1
            "seed": 7, "accent": ACCENTS[theme_for(film)], "theme": theme_for(film), "format": film.get("format", ""),
            "shots": shots, "subs": subs}


THEME_WORDS = {  # topic words -> the animated graphics' colour theme (anim.js THEMES); first match wins
    "heritage": r"histor|temple|chola|pandya|chera|king|queen|empire|ancient|fort|dynasty|heritage|kallanai|ruins|பழமை|கோயில்|சோழ",
    "space": r"space|moon|planet|star\b|stars|sun\b|galax|orbit|rocket|astronaut|nasa|isro|நிலா|விண்",
    "ocean": r"ocean|sea\b|fish|octopus|whale|shark|coral|river|rain|கடல்",
    "tech": r"\bai\b|artificial|robot|phone|computer|internet|battery|software|machine learning|technology|chip",
    "nature": r"animal|forest|plant|tree|bird|insect|jungle|flower|nature|snake|elephant|tiger|\bcats?\b|\bdogs?\b",
}
ACCENTS = {"night": "#ffd21f", "heritage": "#ffb43a", "ocean": "#3fe0c5", "nature": "#c8f05a", "space": "#ffd21f",
           "tech": "#2ef0ff", "kids": "#ffd21f"}


def theme_for(film: dict) -> str:
    """The graphics theme that fits the film: kids films are bright, others follow the topic words."""
    if film.get("for_kids") or film.get("category") == "kids":
        return "kids"
    text = " ".join([film.get("title", ""), film.get("en_title", ""), " ".join(film.get("tags", []))]).lower()
    for name, pat in THEME_WORDS.items():
        if re.search(pat, text):
            return name
    return "night"


def mix_audio(film: dict, plan_t: dict, work: Path, out: Path) -> float:
    """One finished sound track (every line at its voiceStart, music ducked under it) -> out (mp3). Returns its length."""
    # Voice track: silence, line 0, gap, line 1, ... with each line placed at its voiceStart.
    inputs, filters = [], []
    for i, s in enumerate(plan_t["shots"]):
        inputs += ["-i", str(work / f"line-{i}.mp3")]
        filters.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo,adelay={round(s['voiceStart'] * 1000)}:all=1[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(plan_t["shots"])))
    total = plan_t["duration"]
    voice = work / "voice.wav"
    run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex",
         ";".join(filters) + f";{mix}amix=inputs={len(plan_t['shots'])}:normalize=0,"
         f"loudnorm=I=-16:TP=-2:LRA=9,apad,atrim=0:{total:.3f}[out]",
         "-map", "[out]", "-ar", "44100", "-ac", "2", str(voice)], "voice track")

    # Background music, composed for this film; it ducks under the voice. Without it the film still renders.
    level = MUSIC_LEVEL[sound_of(film)["music"]]
    try:
        if not level:
            raise ValueError("turned off for this film")
        from . import music
        bed = music.make(music.preset_for(film), total, work / "music.wav", seed=sum(map(ord, film.get("title", ""))))
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(voice), "-i", str(bed), "-filter_complex",
             f"[0:a]asplit=2[v][key];[1:a]volume={level}[m];[m][key]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=450[bed];"
             "[v][bed]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-15:TP=-1.5:LRA=11[out]",
             "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", str(out)], "music mix")
    except Exception as e:  # music is a nice-to-have: never lose a film over it
        print(f"music skipped: {e}")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(voice), "-c:a", "libmp3lame", "-b:a", "192k", str(out)], "voice track")
    return total


def assemble(film: dict, plan_t: dict, lengths: list[float], work: Path, project: Path) -> None:
    """Copy the template, write the shot markup, the timing data and one voice track."""
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(TEMPLATE, project)
    assets = project / "assets"
    for f in work.glob("shot-*.jpg"):
        shutil.copy(f, assets / f.name)

    out = assets / "voice.mp3"
    voice_len = mix_audio(film, plan_t, work, out)

    def shot(i: int, s: dict) -> str:
        inner = (f'<div id="anim-{i}"></div>' if s["kind"] == "anim" else f'<div id="scene-{i}"></div>' if s["kind"] == "scene"
                 else f'<img src="assets/shot-{i}.jpg" alt="" />')
        return (f'          <div id="shot-{i}" class="shot clip" data-start="{s["clipStart"]}" '
                f'data-duration="{round(s["clipEnd"] - s["clipStart"], 3)}" data-track-index="0" style="z-index:{i + 1}">'
                f'<div class="fx"><div class="cam">{inner}</div></div></div>')

    # Pictures play inside the framed card; animated graphics take the whole page (index.html: #shots and #gfx).
    shots = list(enumerate(plan_t["shots"]))
    html = (TEMPLATE / "index.html").read_text()
    html = (html.replace("__SHOTS__", "\n".join(shot(i, s) for i, s in shots if s["kind"] not in ("anim", "scene")))
                .replace("__GFX__", "\n".join(shot(i, s) for i, s in shots if s["kind"] in ("anim", "scene")))
                .replace("__DURATION__", str(plan_t["duration"]))
                .replace("__VOICE_DURATION__", f"{voice_len:.3f}"))
    (project / "index.html").write_text(html)
    (assets / "film.js").write_text("window.FILM = " + json.dumps(plan_t, ensure_ascii=False) + ";\n")


def hyperframes(project: Path, *args: str, timeout: int = 1800) -> str:
    env = {**os.environ, "HYPERFRAMES_NO_TELEMETRY": "1", "HYPERFRAMES_SKIP_SKILLS": "1", "CI": "1"}
    done = subprocess.run(["npx", "--yes", HYPERFRAMES, *args], cwd=project, env=env,
                          capture_output=True, text=True, timeout=timeout)
    if done.returncode:
        tail = (done.stdout + done.stderr)[-900:]
        raise StepError(f"hyperframes {args[0]} failed: {tail}")
    return done.stdout


def render(project: Path, out: Path) -> float:
    lint = hyperframes(project, "lint")
    m = re.search(r"(\d+) error", lint)
    if m and int(m.group(1)):
        raise StepError("the film has errors:\n" + lint[-900:])
    # 24 fps: about 20% less render time than 30, and the same on a phone.
    hyperframes(project, "render", "--quality", os.environ.get("SHORTS_QUALITY", "looks"),
                "--fps", os.environ.get("SHORTS_FPS", "24"), "-o", str(out))
    expected = float(re.search(r'data-duration="([\d.]+)"', (project / "index.html").read_text()).group(1))
    got = probe(out)
    if abs(got - expected) > 0.5:
        raise StepError(f"render is {got:.1f}s but the film is {expected:.1f}s")
    if not has_audio(out):
        raise StepError("the rendered video has no sound")
    return got


# ---------------------------------------------------------------- the authored explainer

AUTHOR = HERE / "author"
AUTHOR_MODEL = os.environ.get("SHORTS_AUTHOR_MODEL", "sonnet")
AUTHOR_MINUTES = int(os.environ.get("SHORTS_AUTHOR_MINUTES", "80"))
KIT = ("build.py", "lib.js", "hf", "example-scene.txt")
# The illustrator may only write scenes: the kit, the clock and anything outside the project stay as they are.
AUTHOR_DENY = [f"{t}(./{n})" for t in ("Edit", "Write") for n in (*KIT, "timing.json", "brief.json", "index.html")]


def _kit(project: Path) -> None:
    for name in KIT:
        shutil.copy(AUTHOR / name, project / name)
    shutil.copytree(AUTHOR / "fonts", project / "assets" / "fonts", dirs_exist_ok=True)  # Tamil text needs its font shipped
    (project / "hf").chmod(0o755)


def _claude_author(project: Path, prompt: str, step: str) -> dict:
    """Claude draws and animates the film in `project`, with file tools, the build script and the HyperFrames CLI only."""
    env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": claude_token(), "DISABLE_AUTOUPDATER": "1",
           "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "HYPERFRAMES_NO_TELEMETRY": "1", "HYPERFRAMES_SKIP_SKILLS": "1",
           "CI": "1", "SHORTS_HYPERFRAMES": HYPERFRAMES}
    cmd = ["claude", "-p", prompt, "--model", AUTHOR_MODEL, "--append-system-prompt", (AUTHOR / "AUTHOR.md").read_text(),
           "--output-format", "json", "--permission-mode", "acceptEdits", "--no-session-persistence", "--strict-mcp-config",
           "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep", "Bash(python3 build.py)", "Bash(./hf:*)", "Bash(./hf *)",
           "--disallowedTools", *AUTHOR_DENY, "WebFetch", "WebSearch", "Agent"]
    with tempfile.TemporaryFile("w+") as so, tempfile.TemporaryFile("w+") as se:
        proc = subprocess.Popen(cmd, cwd=project, env=env, stdout=so, stderr=se, text=True)
        end = time.monotonic() + AUTHOR_MINUTES * 60
        while proc.poll() is None:
            if should_stop():
                proc.kill()
                raise Cancelled("cancelled")
            if time.monotonic() > end:
                proc.kill()
                raise StepError(f"drawing the film took more than {AUTHOR_MINUTES} minutes")
            time.sleep(3)
        so.seek(0), se.seek(0)
        stdout, stderr = so.read(), se.read()
    try:
        out = json.loads(stdout)
    except json.JSONDecodeError:
        raise StepError(f"Claude ({step}) failed: {(stderr or stdout)[-400:]}")
    if out.get("is_error"):
        raise StepError(f"Claude ({step}) failed: {str(out.get('result'))[:400]}")
    u = out.get("usage") or {}
    return {"step": step, "model": AUTHOR_MODEL, "cost_usd": round(out.get("total_cost_usd") or 0, 4),
            "input_tokens": u.get("input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
            "cache_read_tokens": u.get("cache_read_input_tokens", 0), "cache_write_tokens": u.get("cache_creation_input_tokens", 0),
            "seconds": round((out.get("duration_ms") or 0) / 1000, 1)}


def _author_errors(project: Path) -> str:
    """Build the project and lint it. "" when it is ready to render."""
    _kit(project)  # always the repo's own kit, whatever happened during authoring
    built = subprocess.run(["python3", "build.py"], cwd=project, capture_output=True, text=True, timeout=120)
    if built.returncode:
        return (built.stdout + built.stderr)[-1500:]
    try:
        lint = hyperframes(project, "lint")
    except StepError as e:
        return str(e)[-1500:]
    m = re.search(r"(\d+) error", lint)
    return lint[-1500:] if m and int(m.group(1)) else ""


def author_clock(film: dict, plan_t: dict) -> dict:
    return {"duration": plan_t["duration"], "endStart": plan_t["endStart"], "subs": plan_t["subs"],
            "shots": [{"i": i, "start": t["start"], "voiceStart": t["voiceStart"], "voiceEnd": t["voiceEnd"], "end": t["end"],
                       "ta": s["ta"], "en": s["en"]} for i, (s, t) in enumerate(zip(film["shots"], plan_t["shots"]))]}


def author_film(film: dict, plan_t: dict, work: Path, project: Path, log=print) -> dict | None:
    """The explainer's picture: Claude writes the scenes as real HyperFrames motion graphics, looks at its own frames
    and fixes them. Scenes read the clock from timing.json, so the same scenes rebuild for another voice (English).
    A retry reuses finished scenes; an owner's change is applied to them once. Returns Claude's usage (None if reused)."""
    (project / "scenes").mkdir(parents=True, exist_ok=True)
    (project / "assets").mkdir(exist_ok=True)
    _kit(project)
    (project / "timing.json").write_text(json.dumps(author_clock(film, plan_t), ensure_ascii=False, indent=1))
    (project / "brief.json").write_text(json.dumps({**film.get("brief", {}), "title": film.get("en_title", ""),
        "shots": [{"i": i, "ta": s["ta"], "en": s["en"], "mood": s["mood"], "picture_idea": s.get("picture", "")}
                  for i, s in enumerate(film["shots"])]}, ensure_ascii=False, indent=1))
    mix_audio(film, plan_t, work, project / "assets" / "voice.mp3")
    usage = None
    lines = hashlib.sha1(json.dumps([s["en"] for s in film["shots"]]).encode()).hexdigest()[:12]
    change = (film.get("author_change") or "").strip()
    mark, state = project / ".authored", f"{lines}|{hashlib.sha1(change.encode()).hexdigest()[:12]}"
    have = (project / "scenes.json").exists() and any((project / "scenes").glob("*.html"))
    if not have:
        log("drawing the film")
        usage = _claude_author(project, "Make this film. Follow AUTHOR.md exactly, work through every step, and finish with DONE.md.", "draw")
    elif (mark.read_text() if mark.exists() else f"{lines}|{hashlib.sha1(b'').hexdigest()[:12]}") != state:  # no mark: a retry of a first draw
        log("redrawing the film")
        ask = (f"The owner watched this film and asks for this change:\n\"\"\"\n{change}\n\"\"\"\n" if change else "") + (
            "brief.json and timing.json are current (lines or timing may have changed). Update scenes.json and the scenes so "
            "the film matches them and does what the owner asks; keep what the change does not touch. Then build, check, "
            "look at your frames, fix, and rewrite DONE.md.")
        usage = _claude_author(project, ask, "redraw")
    for attempt in range(2):
        errors = _author_errors(project)
        if not errors:
            break
        if attempt:
            raise StepError("the drawn film still has errors:\n" + errors[-700:])
        log("fixing the film")
        fix = _claude_author(project, "The build or the HyperFrames lint reports errors. Fix them in the scenes, rebuild, "
                             "and check again:\n\n" + errors, "draw-fix")
        usage = _add_usage(usage, fix) if usage else fix
    mark.write_text(state)
    return usage


# ---------------------------------------------------------------- the lesson's 3D scenes

LESSON = HERE.parent / "lesson"
LESSON_KIT = ("stage.html", "check.py", "example.js", "dress.png", "host.vrm", "AUTHOR.md")  # host.vrm: pixiv sample, VRM licence allows redistribution and commercial use
LESSON_DENY = [f"{t}(./{n})" for t in ("Edit", "Write") for n in (*LESSON_KIT, "lesson.json", "brief.json", "env.json")]


def lesson_json(film: dict, starts: list[float], ends: list[float], dur: float) -> dict:
    """What the stage reads: every line with its times, scene and gestures, and the badge text."""
    label = (film.get("brief") or {}).get("series") or film.get("series") or ""
    part = int(film.get("part") or 1)
    label = f"{label} · {part:02d}" if label and part > 1 else (label or "Know This Daily")
    return {"label": label[:40], "dur": round(dur, 3), "lang": film.get("lang", "ta"), "agenda": film.get("agenda", []),
            "topic": str((film.get("brief") or {}).get("topic") or film.get("en_title") or "")[:80], "lines": [
        {"ta": s["ta"], "en": s["en"], "scene": s.get("scene", i), "start": round(a, 3), "end": round(b, 3),
         "act": [[x["at"], x["pose"]] + ([x["face"]] if x.get("face") else []) for x in s.get("act", [])]}
        for i, (s, a, b) in enumerate(zip(film["shots"], starts, ends))]}


def lesson_kit(stage: Path) -> None:
    stage.mkdir(parents=True, exist_ok=True)
    for n in LESSON_KIT:
        shutil.copy(LESSON / n, stage / n)


def _lesson_errors(stage: Path) -> str:
    lesson_kit(stage)
    done = subprocess.run(["python3", "check.py"], cwd=stage, capture_output=True, text=True, timeout=600)
    return "" if done.returncode == 0 else (done.stdout + done.stderr)[-1500:]


def author_lesson(film: dict, stage: Path, log=print) -> dict | None:
    """Claude writes stations.js (the 3D props of every scene) in `stage`, checks it, looks at stills, fixes.
    lesson.json there may hold estimated timing: the scenes time themselves to K.at(k), so real timing fits later."""
    lesson_kit(stage)
    (stage / "brief.json").write_text(json.dumps({**film.get("brief", {}), "title": film.get("en_title", ""), "scenes": [
        {"scene": s["scene"], "picture": s.get("picture", ""), "models": [o["slug"] for o in s.get("objects", [])],
         "lines": [x["en"] for x in film["shots"] if x["scene"] == s["scene"]]}
        for s in film["shots"] if s.get("picture")]}, ensure_ascii=False, indent=1))
    change = (film.get("author_change") or "").strip()
    env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": claude_token(), "DISABLE_AUTOUPDATER": "1",
           "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "CI": "1"}

    def claude(prompt: str, step: str) -> dict:
        """Claude with file tools and check.py only; every tool call is printed as it happens (the job log shows progress)."""
        cmd = ["claude", "-p", prompt, "--model", AUTHOR_MODEL, "--append-system-prompt", (LESSON / "AUTHOR.md").read_text(),
               "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits", "--no-session-persistence",
               "--strict-mcp-config", "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep", "Bash(python3 check.py)",
               "Bash(python3 check.py:*)", "Bash(python3 check.py *)", "--disallowedTools", *LESSON_DENY, "WebFetch", "WebSearch", "Agent"]
        t0, out, tail = time.monotonic(), None, []
        proc = subprocess.Popen(cmd, cwd=stage, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            tail = (tail + [line])[-5:]
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "assistant":
                for c in (ev.get("message") or {}).get("content", []):
                    if c.get("type") == "tool_use":
                        i = c.get("input") or {}
                        what = i.get("command") or i.get("file_path") or i.get("pattern") or ""
                        log(f"{(time.monotonic() - t0) / 60:4.1f} min  {c.get('name')} {str(what).replace(str(stage) + '/', '')[:120]}")
            elif ev.get("type") == "result":
                out = ev
            if time.monotonic() - t0 > AUTHOR_MINUTES * 60:
                proc.kill()
                raise StepError(f"drawing the scenes took more than {AUTHOR_MINUTES} minutes")
        proc.wait()
        if not out:
            raise StepError(f"Claude ({step}) failed: {''.join(tail)[-400:]}")
        if out.get("is_error"):
            raise StepError(f"Claude ({step}) failed: {str(out.get('result'))[:400]}")
        u = out.get("usage") or {}
        return {"step": step, "model": AUTHOR_MODEL, "cost_usd": round(out.get("total_cost_usd") or 0, 4),
                "input_tokens": u.get("input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
                "cache_read_tokens": u.get("cache_read_input_tokens", 0), "cache_write_tokens": u.get("cache_creation_input_tokens", 0),
                "seconds": round((out.get("duration_ms") or 0) / 1000, 1)}

    if (stage / "stations.js").exists() and change:
        log("redrawing the scenes")
        usage = claude(f"The owner watched this lesson and asks for this change:\n\"\"\"\n{change}\n\"\"\"\nlesson.json and brief.json are "
                       "current. Update stations.js so it matches them and does what the owner asks; keep what the change does not "
                       "touch. Then check, look at a few stills, fix, and rewrite DONE.md.", "lesson-redraw")
    elif (stage / "stations.js").exists():
        usage = None  # a retry: the scenes are already written
    else:
        log("drawing the scenes")
        usage = claude("Make the 3D scenes of this lesson. Read AUTHOR.md, example.js, brief.json and lesson.json, write "
                       "stations.js with one entry per scene, check it, look at stills of every scene, fix, and finish with DONE.md.",
                       "lesson-draw")
        log("reviewing the scenes")
        # A second, fresh look: the owner rejects any object that is not instantly recognisable and correct.
        review = claude("You are the strict reviewer of these 3D scenes, not their author. Read AUTHOR.md (the section 'Accuracy: "
                        "the owner's first rule' above all), brief.json and lesson.json. Run python3 check.py with one time per "
                        "scene (a moment after its last reveal) and read every still. For each scene ask: would a child name every "
                        "object correctly at first glance? Is anything made of primitives that should have been the picture? Do "
                        "objects overlap, touch the edges, hide behind the host or the captions? Fix every failure in stations.js "
                        "(replace with the picture or a clean graphic, or remove it), check again, and write REVIEW.md: one line "
                        "per scene, what you changed or 'ok'.", "lesson-review")
        usage = _add_usage(usage, review)
    for attempt in range(2):
        errors = _lesson_errors(stage)
        if not errors:
            return usage
        if attempt:
            raise StepError("the lesson scenes still have errors:\n" + errors[-700:])
        log("fixing the scenes")
        fix = claude("python3 check.py reports errors. Fix them in stations.js and run it again until it prints ok:\n\n" + errors,
                     "lesson-fix")
        usage = _add_usage(usage, fix) if usage else fix
    return usage


# ---------------------------------------------------------------- helpers

def run(cmd: list[str], step: str) -> str:
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode:
        raise StepError(f"{step}: {(done.stderr or done.stdout)[-400:]}")
    return done.stdout


def probe(path: Path) -> float:
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], "probe").strip())


def has_audio(path: Path) -> bool:
    out = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)], "probe")
    return "audio" in out


def preview(src: Path, dest: Path, seconds: float, limit_mb: float = 44) -> None:
    """A copy under Telegram's 50 MB bot limit; YouTube gets the full-quality original."""
    if src.stat().st_size < limit_mb * 1e6:
        shutil.copy(src, dest)
        return
    kbps = int(min(8000, limit_mb * 8000 / seconds) - 160)  # leave room for the sound
    tmp = dest.with_suffix(".part.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-c:v", "libx264", "-preset", "faster", "-crf", "21",
         "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart", str(tmp)], "preview")
    if tmp.stat().st_size >= 49.5e6:
        raise StepError(f"preview is still {tmp.stat().st_size / 1e6:.0f} MB")
    tmp.replace(dest)


def make_video(film: dict, job: Path, log=print) -> dict:
    """Shot list -> checked MP4 at job/video.mp4. Returns facts about the run."""
    work = job / "work"
    work.mkdir(parents=True, exist_ok=True)
    for old in [*work.glob("shot-*.jpg"), *work.glob("line-*.mp3")]:
        old.unlink()  # an edit can have fewer shots; never carry the old ones into the new film
    t = time.monotonic()
    log("pictures and voice")
    # At the same time: the voice is made on the TTS box's CPU (slow), the pictures on free GPUs.
    voice_gpu_done.clear()
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        voice_job = ex.submit(voices, film, work, job.parent.parent / "cache" / "voice")
        voice_gpu_done.wait(240)  # the voice books the free GPU first; pictures have other free sources
        sources = pictures(film, work, job.parent.parent / "cache" / "pictures")
        lengths, voice_engine = voice_job.result()
    plan_t = timeline(film, lengths)
    usage = None
    if film.get("format") == "explainer":  # drawn by Claude to the finished voice, not assembled from the template
        usage = author_film(film, plan_t, work, job / "project", log)
        sources = {"drawn": len(film["shots"])}
    else:
        log("assemble")
        assemble(film, plan_t, lengths, work, job / "project")
    log("render")
    tmp = job / "video.part.mp4"
    seconds = render(job / "project", tmp)
    tmp.replace(job / "video.mp4")
    log("preview")
    preview(job / "video.mp4", job / "preview.mp4", seconds)
    return {**({"usage": usage} if usage else {}),
            "seconds": round(seconds, 1), "shots": len(film["shots"]), "picture_sources": sources, "voice": voice_engine,
            "build_minutes": round((time.monotonic() - t) / 60, 1), "size_mb": round((job / "video.mp4").stat().st_size / 1e6, 1),
            "preview_mb": round((job / "preview.mp4").stat().st_size / 1e6, 1)}


if __name__ == "__main__":
    import sys

    if sys.argv[1:2] == ["plan"]:
        print(json.dumps(make_plan(" ".join(sys.argv[2:]) or None, [], []), ensure_ascii=False, indent=1))
    elif sys.argv[1:2] == ["film"]:
        plan = json.loads(Path(sys.argv[2]).read_text())
        film, usage = write_film(plan)
        out = Path(sys.argv[3])
        out.mkdir(parents=True, exist_ok=True)
        (out / "film.json").write_text(json.dumps(film, ensure_ascii=False, indent=1))
        print(json.dumps(usage))
        print(json.dumps(make_video(film, out)))
    else:
        raise SystemExit(__doc__)
