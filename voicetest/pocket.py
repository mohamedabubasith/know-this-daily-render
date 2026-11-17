"""Pocket TTS Tamil (voice geetha) on CPU: each test line, with timings."""
import sys, time
from pathlib import Path
import numpy as np, soundfile as sf
from huggingface_hub import hf_hub_download
from pocket_tts import TTSModel

here, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
t = time.monotonic()
model = TTSModel.load_model(config="hf://prasadvittaldev/pocket-tts-tamil-female-audiobook/config.yaml", quantize=True)
model.to("cpu")
state = model.get_state_for_audio_prompt(hf_hub_download("prasadvittaldev/pocket-tts-tamil-female-audiobook", "voice_prompt.wav"))
print(f"model loaded in {time.monotonic() - t:.0f}s", flush=True)
for i, line in enumerate((here / "lines.txt").read_text().splitlines()):
    t = time.monotonic()
    chunks = list(model.generate_audio_stream(model_state=state, text_to_generate=line))
    a = np.concatenate([np.asarray(c).reshape(-1) for c in chunks])
    sf.write(out / f"pocket-line{i + 1}.wav", a, 24000)
    print(f"line {i + 1}: {len(a) / 24000:.1f}s of speech in {time.monotonic() - t:.1f}s", flush=True)
