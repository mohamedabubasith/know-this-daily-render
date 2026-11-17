"""OmniVoice on CPU: each test line in the Kayal voice (cloned from voicetest/kayal.mp3), with timings."""
import os, sys, time
from pathlib import Path
import soundfile as sf
import torch
from omnivoice import OmniVoice

here = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
torch.set_num_threads(os.cpu_count() or 4)
t = time.monotonic()
model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cpu", dtype=torch.float32, asr_device="cpu")
print(f"model loaded in {time.monotonic() - t:.0f}s", flush=True)
for steps in (32, 16):
    for i, line in enumerate((here / "lines.txt").read_text().splitlines()):
        t = time.monotonic()
        audio = model.generate(text=line, ref_audio=str(here / "kayal.mp3"), num_step=steps)
        sf.write(out / f"omnivoice-{steps}steps-line{i + 1}.wav", audio[0], 24000)
        print(f"{steps} steps, line {i + 1}: {len(audio[0]) / 24000:.1f}s of speech in {time.monotonic() - t:.0f}s", flush=True)
