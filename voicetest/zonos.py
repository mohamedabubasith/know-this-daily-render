"""ZONOS3-Mini on CPU: each test line in the Kayal voice (cloned from voicetest/kayal.mp3), with timings."""
import base64, os, sys, time
from pathlib import Path
import torch
from zonos3.generation import SAMPLE_RATE
from zonos3.tts.audio import write_pcm16_wav
from zonos3.reference.lm import Zonos3LM
from zonos3.reference.synth import ReferenceAssets, synthesize
from zonos3.utils import release
from zonos3.models.text_extra import TextExtraRows

here = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
torch.set_num_threads(os.cpu_count() or 4)
t = time.monotonic()
cpu = torch.device("cpu")
lm = Zonos3LM.load(release.RELEASE_LM, device=cpu, dtype=torch.float32)
assets = ReferenceAssets.load(steer_bundle=None, accent_adapters=None, laci_heads={})
assets.grow(lm)
lm.append_text_rows(TextExtraRows.load(release.RELEASE_TEXT_ROWS))
print(f"model loaded in {time.monotonic() - t:.0f}s", flush=True)
ref = base64.b64encode((here / "kayal.mp3").read_bytes()).decode()
for i, line in enumerate((here / "lines.txt").read_text().splitlines()):
    t = time.monotonic()
    r = synthesize(lm, {"text": line, "language": "ta", "speaker_audio_base64": ref}, assets=assets, device=cpu, dtype=torch.float32)
    write_pcm16_wav(str(out / f"zonos3-line{i + 1}.wav"), r.pcm, SAMPLE_RATE)
    print(f"line {i + 1}: {len(r.pcm) / SAMPLE_RATE:.1f}s of speech in {time.monotonic() - t:.0f}s", flush=True)
