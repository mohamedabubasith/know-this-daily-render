"""Pocket TTS Tamil (voice geetha, MIT, CPU): python pocket_voice.py UNITS_JSON

UNITS_JSON: [{"text": one sentence, "out": WAV path}, ...]. Each sentence becomes a 24 kHz 16-bit mono WAV; part.py
joins them into lines with the narrator's pauses. Runs in its own venv (torch CPU + pocket-tts)."""
import json, sys, time
from pathlib import Path
import numpy as np, soundfile as sf
from huggingface_hub import hf_hub_download
from pocket_tts import TTSModel

REPO = "prasadvittaldev/pocket-tts-tamil-female-audiobook"
t = time.monotonic()
model = TTSModel.load_model(config=f"hf://{REPO}/config.yaml", quantize=True)
model.to("cpu")
state = model.get_state_for_audio_prompt(hf_hub_download(REPO, "voice_prompt.wav"))
print(f"pocket model loaded in {time.monotonic() - t:.0f}s", flush=True)
for u in json.loads(Path(sys.argv[1]).read_text()):
    t = time.monotonic()
    a = np.concatenate([np.asarray(c).reshape(-1) for c in model.generate_audio_stream(model_state=state, text_to_generate=u["text"])])
    Path(u["out"]).parent.mkdir(parents=True, exist_ok=True)
    sf.write(u["out"], a.astype(np.float32), 24000, subtype="PCM_16")
    print(f"  {len(u['text'])} letters: {len(a) / 24000:.1f}s in {time.monotonic() - t:.1f}s", flush=True)
