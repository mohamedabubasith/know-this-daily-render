"""Background music composed in code and played with FluidSynth + FluidR3_GM (both open source, MIT soundfont).

Every piece is new, so there is nothing to license and nothing YouTube can claim. A mood picks the key, tempo,
chords and instruments; a seed varies the melody, so two films with the same mood still sound different.

    python -m shorts.music kids 60 out.wav
"""

from __future__ import annotations

import random
import subprocess
import tempfile
from pathlib import Path

import mido

SOUNDFONT = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
MAJ, MIN, MAJ7, MIN7 = (0, 4, 7), (0, 3, 7), (0, 4, 7, 11), (0, 3, 7, 10)

# GM programs (0-based): 0 piano, 8 celesta, 9 glockenspiel, 11 vibraphone, 12 marimba, 32 acoustic bass,
# 33 finger bass, 42 cello, 43 contrabass, 45 pizzicato, 46 harp, 47 timpani, 48 strings, 49 slow strings,
# 61 brass section, 89 warm pad, 95 sweep pad.
PRESETS = {
    "kids":       dict(bpm=92, key=60, chords=[(0, MAJ), (7, MAJ), (9, MIN), (5, MAJ)], pad=48, arp=46, lead=8, bass=45, bell=9, melody=True),
    "happy":      dict(bpm=106, key=62, chords=[(0, MAJ), (5, MAJ), (9, MIN), (7, MAJ)], pad=48, arp=12, lead=11, bass=32, shaker=True, melody=True),
    "calm":       dict(bpm=74, key=65, chords=[(0, MAJ7), (9, MIN7), (5, MAJ7), (7, MAJ)], pad=49, arp=0, bass=42),
    "curious":    dict(bpm=98, key=64, chords=[(0, MIN), (8, MAJ), (3, MAJ), (10, MAJ)], pad=89, arp=46, lead=11, bass=33, shaker=True, melody=True),
    "mysterious": dict(bpm=68, key=57, chords=[(0, MIN), (8, MAJ), (5, MIN), (7, MAJ)], pad=95, arp=8, bass=42, sparse=True),
    "epic":       dict(bpm=88, key=62, chords=[(0, MIN), (8, MAJ), (3, MAJ), (10, MAJ)], pad=48, arp=48, bass=43, brass=61, timpani=True),
    "tense":      dict(bpm=100, key=52, chords=[(0, MIN), (1, MAJ), (0, MIN), (10, MAJ)], pad=89, arp=48, bass=43, pulse=True),
    "sad":        dict(bpm=66, key=57, chords=[(0, MIN), (5, MIN), (10, MAJ), (3, MAJ)], pad=49, arp=0, bass=42),
}
MOOD_TO_PRESET = {"mysterious": "mysterious", "dramatic": "epic", "epic": "epic", "happy": "happy", "excited": "happy",
                  "calm": "calm", "curious": "curious", "tense": "tense", "sad": "sad"}
PENTA = (0, 2, 4, 7, 9)


def preset_for(film: dict) -> str:
    if film.get("for_kids"):
        return "kids"
    moods = [s.get("mood") for s in film.get("shots", [])]
    top = max(set(moods), key=moods.count) if moods else "curious"
    return MOOD_TO_PRESET.get(top, "curious")


def compose(name: str, seconds: float, seed: int) -> mido.MidiFile:
    p = PRESETS[name]
    rnd = random.Random(seed)
    tpb = 480
    bar = tpb * 4
    bars = int(seconds * p["bpm"] / 240) + 2
    mid = mido.MidiFile(ticks_per_beat=tpb)
    events: dict[int, list] = {}  # channel -> [(abs_tick, msg)]

    def note(ch, tick, n, length, vel):
        vel = max(1, min(127, vel + rnd.randint(-6, 6)))
        events.setdefault(ch, []).append((tick, mido.Message("note_on", channel=ch, note=n, velocity=vel)))
        events.setdefault(ch, []).append((tick + length, mido.Message("note_off", channel=ch, note=n, velocity=0)))

    programs = {0: p["pad"], 1: p["arp"], 2: p.get("lead", p["arp"]), 3: p["bass"], 4: p.get("brass", 0), 5: p.get("bell", 9), 6: 47}
    for ch, prog in programs.items():
        events.setdefault(ch, []).append((0, mido.Message("program_change", channel=ch, program=prog)))
        events[ch].append((0, mido.Message("control_change", channel=ch, control=91, value=70)))  # reverb send
    events[0].append((0, mido.Message("control_change", channel=0, control=7, value=70)))  # pad sits back

    prev = p["key"] + 12
    for b in range(bars):
        t0 = b * bar
        root, quality = p["chords"][b % len(p["chords"])]
        chord = [p["key"] + root + i for i in quality]
        last = b == bars - 1
        # Pad: the whole chord, held.
        for n in chord:
            note(0, t0, n, bar * (2 if last else 1) - 10, 52)
        # Bass: root on beat 1 (pulsing eighths when tense, plucked quarters for kids).
        bn = p["key"] + root - 24 + (12 if p["bass"] in (45, 42) else 0)
        if p.get("pulse"):
            for k in range(8):
                note(3, t0 + k * tpb // 2, bn, tpb // 2 - 30, 70)
        elif p["bass"] == 45:
            for k in range(4):
                note(3, t0 + k * tpb, bn + (7 if k % 2 else 0), tpb // 2, 64)
        else:
            note(3, t0, bn, bar - 20, 72)
        if last:
            break
        # Arpeggio over the chord.
        tones = [n + 12 for n in chord] + [chord[0] + 24]
        step = tpb if p.get("sparse") else tpb // 2
        for k in range(bar // step):
            if p.get("sparse") and rnd.random() < 0.45:
                continue
            note(1, t0 + k * step, tones[(k * 2 + b) % len(tones)], step - 20, 58 if k % 2 else 66)
        # Melody: chord tones and pentatonic steps, a short phrase per bar.
        if p.get("melody"):
            rhythm = rnd.choice([[2, 1, 1], [1, 1, 2], [1, 1, 1, 1], [3, 1], [2, 2]])
            t = t0
            for beats in rhythm:
                cand = [p["key"] + 12 + root + i for i in quality] + [p["key"] + 12 + i for i in PENTA]
                cand = [c + 12 if c < 70 else c for c in cand]
                cand.sort(key=lambda c: abs(c - prev) + rnd.random() * 4)
                prev = cand[0] if rnd.random() < 0.7 else cand[1]
                note(2, t, prev, beats * tpb - 30, 78)
                t += beats * tpb
        # Colour: bells for kids, brass and timpani for epic, a soft shaker for upbeat moods.
        if p.get("bell") and b % 2 == 1:
            note(5, t0 + 3 * tpb, chord[0] + 24, tpb, 50)
        if p.get("brass") and b % 2 == 0:
            for n in chord:
                note(4, t0, n, bar - 40, 46)
        if p.get("timpani") and b % 4 == 0:
            note(6, t0, p["key"] + root - 24, tpb, 90)
        if p.get("shaker"):
            for k in range(8):
                note(9, t0 + k * tpb // 2, 70, tpb // 4, 34 if k % 2 else 22)

    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(p["bpm"])))
    mid.tracks.append(meta)
    for ch, evs in sorted(events.items()):
        track = mido.MidiTrack()
        last = 0
        for tick, msg in sorted(evs, key=lambda e: (e[0], e[1].type == "note_on")):
            track.append(msg.copy(time=tick - last))
            last = tick
        mid.tracks.append(track)
    return mid


def make(name: str, seconds: float, out: Path, seed: int = 1) -> Path:
    """A finished background track: `seconds` long, faded in and out, at a quiet bed level (-24 LUFS)."""
    with tempfile.TemporaryDirectory() as tmp:
        midi, raw = Path(tmp) / "m.mid", Path(tmp) / "m.wav"
        compose(name, seconds, seed).save(midi)
        subprocess.run(["fluidsynth", "-ni", "-q", "-g", "0.7", "-r", "44100", "-F", str(raw), SOUNDFONT, str(midi)],
                       check=True, capture_output=True, timeout=300)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af",
                        f"atrim=0:{seconds:.2f},afade=t=in:d=1.2,afade=t=out:st={max(0.0, seconds - 2.5):.2f}:d=2.5,"
                        "highpass=f=60,loudnorm=I=-24:TP=-3:LRA=11", "-ar", "44100", "-ac", "2", str(out)],
                       check=True, capture_output=True, timeout=300)
    return out


if __name__ == "__main__":
    import sys

    print(make(sys.argv[1], float(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 1))
