"""The host's mouth and beat timing from the voice-only track: opens on each syllable, shut in pauses.

    envelope(wav) -> {"fps": 30, "open": [...per frame 0..1], "beats": [seconds of stressed syllables]}
"""
import json
import subprocess
import sys

import numpy as np


def envelope(wav: str, fps: int = 30) -> dict:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", wav, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 160  # 10 ms
    n = max(1, len(x) // hop - 2)
    env = np.sqrt(np.convolve(x[: (n + 2) * hop] ** 2, np.ones(2 * hop) / (2 * hop), "valid")[::hop][:n])
    env = np.convolve(env, np.ones(3) / 3, "same")
    loud = env[env > env.max() * 0.05]
    ref = float(np.percentile(loud, 90)) if len(loud) else 1.0

    def roll(a, k, f):
        p = np.pad(a, k, mode="edge")
        w = np.lib.stride_tricks.sliding_window_view(p, 2 * k + 1)
        return f(w, axis=1)

    hi, lo = roll(env, 20, np.max), roll(env, 8, np.min)
    syl = np.clip((env - lo) / (hi - lo + 1e-6), 0, 1)
    o = (0.35 + 0.65 * syl) * np.clip(env / ref, 0, 1) ** 0.5
    o[env < ref * 0.07] = 0
    o = np.where(o < 0.12, 0, (o - 0.12) / 0.88)
    frames = int(len(o) / 100 * fps)
    opens = [round(float(o[min(len(o) - 1, int(i / fps * 100))]), 3) for i in range(frames)]
    beats, last = [], -99
    for i in range(5, len(env) - 5):
        if env[i] == env[i - 5:i + 6].max() and env[i] > ref * 0.55 and env[i] - env[max(0, i - 15):i + 16].min() > ref * 0.35 and i - last >= 28:
            beats.append(round(i / 100, 2))
            last = i
    return {"fps": fps, "open": opens, "beats": beats}


if __name__ == "__main__":
    e = envelope(sys.argv[1])
    json.dump(e, open(sys.argv[2], "w"))
    print(len(e["open"]), "frames,", len(e["beats"]), "beats")
