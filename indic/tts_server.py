"""Tamil/English TTS over HTTP, backed by edge-tts (free, no API key).

GET  /            -> "ok"        keepalive probe; n8n pings this every 15 min
GET  /voices      -> JSON        available ta-* and en-* voices
POST /tts         -> audio/mpeg  {"text": "...", "voice": "ta-IN-PallaviNeural"}
POST /indic/jobs       {"text", "rate"} -> {"id", "status"}   queue one line for IndicF5 (AI4Bharat, MIT) on this CPU,
                                                              the channel's narrator cloned from ~/indic/ref.wav
GET  /indic/jobs/{id}  -> audio/mpeg when ready, 202 {"status"} while waiting, 404 unknown, 500 failed

A line takes minutes on CPU, and the instabox port proxy cuts any request after about 20 seconds, so the caller
queues every line and polls. Only the 8081 service (indic-env) can run the model.
"""

import asyncio
import hashlib
import io
import queue
import os
import re
import time
import subprocess
import tempfile
import threading
from pathlib import Path

import edge_tts
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

MAX_CHARS = 5000
DEFAULT_VOICE = "ta-IN-PallaviNeural"

app = FastAPI(title="tts")

# Populated on first use. edge-tts fetches the list over the network, so we do it
# lazily rather than at import time and keep it for the life of the process.
_voices: set[str] = set()
_voices_lock = asyncio.Lock()


async def allowed_voices() -> set[str]:
    global _voices
    async with _voices_lock:
        if not _voices:
            every = await edge_tts.list_voices()
            _voices = {
                v["ShortName"]
                for v in every
                if v["ShortName"].startswith(("ta-", "en-"))
            }
        return _voices


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_CHARS)
    voice: str = DEFAULT_VOICE
    rate: str = "+0%"
    pitch: str = "+0Hz"


@app.get("/", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


@app.get("/voices")
async def voices() -> dict:
    names = sorted(await allowed_voices())
    return {"count": len(names), "voices": names}


@app.post("/tts")
async def tts(req: TTSRequest) -> StreamingResponse:
    if req.voice not in await allowed_voices():
        raise HTTPException(400, f"unknown voice: {req.voice}")

    buf = io.BytesIO()
    communicate = edge_tts.Communicate(
        req.text, req.voice, rate=req.rate, pitch=req.pitch
    )
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])

    if not buf.tell():
        # edge-tts returns an empty stream rather than raising when Microsoft's
        # endpoint rejects the request, so an empty buffer is the only signal.
        raise HTTPException(502, "tts upstream returned no audio")

    buf.seek(0)
    return StreamingResponse(buf, media_type="audio/mpeg")


# ---------------------------------------------------------------- IndicF5

INDIC = Path.home() / "indic"
_model = None
_model_lock = threading.Lock()  # one line at a time: the model already uses every CPU core


def _speed(rate: str) -> float:
    """The mood's small speed nudge, on top of the narrator's calm pace (kept within 6%, or it sounds rushed)."""
    m = re.fullmatch(r"([+-]\d+)%", rate.strip())
    return min(1.06, max(0.94, 1 + int(m.group(1)) / 100)) if m else 1.0


# The narrator's pace and breaths. The owner found 1.0 too fast for a Tamil voice-over. Changing these changes the
# voice, so VOICE_VERSION goes into every line's id and old lines are not reused.
PACE = float(os.environ.get("INDIC_PACE", "0.80"))  # 0.85 still rushed words (owner, 2026-11-18)
BREATH = {".": 0.42, "!": 0.42, "?": 0.48, "…": 0.6, "...": 0.6}  # silence after each sentence, like a voice-over artist
# The reference clip is part of the voice too (2026-11-17: the owner chose sample G, the Rasa storytelling clip).
_REF_ID = hashlib.sha1((INDIC / "ref.wav").read_bytes()).hexdigest()[:8] if (INDIC / "ref.wav").exists() else "none"
STEPS = int(os.environ.get("INDIC_STEPS", "32"))  # 32 = the owner's best quality; 16 is about twice as fast
VOICE_VERSION = f"paced-{PACE}-{_REF_ID}" + ("" if STEPS == 32 else f"-s{STEPS}")


def _sentences(text: str) -> list[tuple[str, float]]:
    """A line in sentences, each with the pause after it. A voice-over artist breathes between sentences; the model,
    given the whole line, runs them together."""
    out = []
    for m in re.finditer(r"(.+?)(\.\.\.|…|[.!?])(?=\s|$)|(.+?)$", text.strip(), re.S):
        body = (m.group(1) or m.group(3) or "").strip()
        end = m.group(2) or ""
        if body:
            out.append((body + (end if end in ".!?" else ","), BREATH.get(end, 0.0)))
    return out or [(text, 0.0)]


def _load() -> None:
    """The model and the reference voice in memory (call with _model_lock held). No audio is made."""
    global _model
    if _model is None:
        import os

        import torch
        from f5_tts.infer.utils_infer import preprocess_ref_audio_text
        from transformers import AutoModel

        # The model's own code fetches vocab.txt from the gated repo without passing a token.
        os.environ.setdefault("HF_TOKEN", (Path.home() / ".config/indic/hf-token").read_text().strip())
        torch.set_num_threads(os.cpu_count() or 4)
        t0 = time.monotonic()
        model = AutoModel.from_pretrained("ai4bharat/IndicF5", trust_remote_code=True)
        ref = preprocess_ref_audio_text(str(INDIC / "ref.wav"), (INDIC / "ref.txt").read_text().strip())
        _model = (model, ref)
        print(f"model loaded in {time.monotonic() - t0:.0f}s", flush=True)


@app.post("/indic/load")
def indic_load() -> dict:
    """Start loading the model now (the GitHub voice runners do this while Claude writes the script)."""
    def go():
        with _model_lock:
            _load()
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True}


def _indic_mp3(text: str, rate: str, raw: bool = False) -> bytes:
    """The line as MP3; raw=True: one sentence exactly as given, as a 16-bit WAV with no pause or filter (the GitHub
    render makes sentences on many runners and joins them itself)."""
    import numpy as np  # here, not at the top: the 8080 keepalive service runs without these packages
    import soundfile as sf

    with _model_lock:
        _load()
        import torch
        from f5_tts.infer.utils_infer import infer_process

        model, (ref_audio, ref_text) = _model
        parts = []
        for sentence, pause in ([(text, 0.0)] if raw else _sentences(text)):
            t1 = time.monotonic()
            with torch.inference_mode():
                # 32 steps by default: the owner chose best quality (about 30 s of CPU per second of speech).
                a, _, _ = infer_process(ref_audio, ref_text, sentence, model.ema_model, model.vocoder,
                                        mel_spec_type="vocos", speed=PACE, device="cpu", nfe_step=STEPS)
            print(f"{len(sentence)} letters voiced in {time.monotonic() - t1:.0f}s", flush=True)
            a = np.asarray(a)
            if a.dtype == np.int16:
                a = a.astype(np.float32) / 32768.0
            parts += [a.astype(np.float32), np.zeros(int(24000 * pause), dtype=np.float32)]
    audio = np.concatenate(parts)
    with tempfile.TemporaryDirectory() as tmp:
        if raw:
            sf.write(Path(tmp) / "raw.wav", audio, 24000, subtype="PCM_16")
            return (Path(tmp) / "raw.wav").read_bytes()
        wav, mp3 = Path(tmp) / "a.wav", Path(tmp) / "a.mp3"
        sf.write(wav, audio.astype(np.float32), 24000)
        # Speed for the mood, trimmed silence at both ends, and a level that matches edge-tts.
        af = (f"atempo={_speed(rate):.3f},silenceremove=start_periods=1:start_threshold=-45dB,"
              "areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,loudnorm=I=-16:TP=-1.5")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af", af, "-ar", "24000",
                        "-ac", "1", "-b:a", "96k", str(mp3)], check=True, timeout=120)
        return mp3.read_bytes()


class IndicRequest(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    rate: str = "+0%"
    raw: bool = False


OUT = INDIC / "out"
_jobs: dict[str, str] = {}  # id -> "queued" | "working" | "error: ..."; finished lines are files in OUT
_q: "queue.Queue[tuple[str, str, str, bool]]" = queue.Queue()
_worker: threading.Thread | None = None


def _work() -> None:
    while True:
        jid, text, rate, raw = _q.get()
        _jobs[jid] = "working"
        try:
            data = _indic_mp3(text, rate, raw)
            tmp = OUT / f"{jid}.part"
            tmp.write_bytes(data)
            tmp.replace(OUT / f"{jid}.mp3")
            _jobs.pop(jid, None)
        except Exception as e:  # noqa: BLE001 - reported to the caller, who falls back to edge-tts
            _jobs[jid] = f"error: {e}"[:300]


@app.post("/indic/jobs")
def indic_submit(req: IndicRequest) -> dict:
    global _worker
    if not (Path.home() / ".config/indic/hf-token").exists():
        raise HTTPException(503, "IndicF5 is not set up on this box")
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.mp3"):  # keep a week of finished lines
        if old.stat().st_mtime < time.time() - 7 * 86400:
            old.unlink(missing_ok=True)
    jid = hashlib.sha1(f"{VOICE_VERSION}|{req.rate}|{req.raw}|{req.text}".encode()).hexdigest()[:16]
    if (OUT / f"{jid}.mp3").exists():
        return {"id": jid, "status": "done"}
    if jid not in _jobs or _jobs[jid].startswith("error"):
        _jobs[jid] = "queued"
        _q.put((jid, req.text, req.rate, req.raw))
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_work, daemon=True)
        _worker.start()
    return {"id": jid, "status": _jobs[jid], "queued": _q.qsize()}


@app.get("/indic/jobs/{jid}")
def indic_result(jid: str):
    if not re.fullmatch(r"[0-9a-f]{16}", jid):
        raise HTTPException(400, "bad id")
    f = OUT / f"{jid}.mp3"
    if f.exists():
        return FileResponse(f, media_type="audio/mpeg")
    st = _jobs.get(jid)
    if st is None:
        raise HTTPException(404, "unknown line: submit it again")
    if st.startswith("error"):
        raise HTTPException(500, st)
    return JSONResponse({"status": st, "queued": _q.qsize()}, status_code=202)
