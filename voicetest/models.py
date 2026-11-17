"""python models.py MODEL LINES OUT: every line with one CPU voice model, timed. MODEL: pocket | rasa | kuyil | spring"""
import os, sys, time
from pathlib import Path
import numpy as np, soundfile as sf
m, lines, out = sys.argv[1], Path(sys.argv[2]).read_text().splitlines(), Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
t = time.monotonic()
if m == "pocket":
    from huggingface_hub import hf_hub_download
    from pocket_tts import TTSModel
    R = "prasadvittaldev/pocket-tts-tamil-female-audiobook"
    model = TTSModel.load_model(config=f"hf://{R}/config.yaml", quantize=True); model.to("cpu")
    st = model.get_state_for_audio_prompt(hf_hub_download(R, "voice_prompt.wav"))
    say = lambda x: (np.concatenate([np.asarray(c).reshape(-1) for c in model.generate_audio_stream(model_state=st, text_to_generate=x)]), 24000)
elif m == "rasa":
    import torch
    from transformers import AutoModel, AutoTokenizer
    model = AutoModel.from_pretrained("ai4bharat/vits_rasa_13", trust_remote_code=True).eval()
    tok = AutoTokenizer.from_pretrained("ai4bharat/vits_rasa_13", trust_remote_code=True)
    def say(x):
        with torch.inference_mode():
            return model(tok(text=x, return_tensors="pt")["input_ids"], speaker_id=18, emotion_id=3).waveform.squeeze().numpy(), model.config.sampling_rate
elif m == "kuyil":
    sys.path.insert(0, os.path.expanduser("~/kuyil"))
    import synth
    speak, _ = synth.load(os.path.expanduser("~/kuyil/kuyil-5m"))
    say = lambda x: (np.asarray(speak(x, "female")), 16000)
elif m == "spring":
    from transformers import AutoModel
    model = AutoModel.from_pretrained("SPRINGLab/SPRING_F5", trust_remote_code=True)
    ref = Path(__file__).parent.parent / "indic"
    def say(x):
        a = model(x, ref_audio_path=str(ref / "ref.wav"), ref_text=(ref / "ref.txt").read_text().strip(), lang="ta")
        return (a.astype(np.float32) / 32768.0 if a.dtype == np.int16 else a), 24000
print(f"{m} loaded in {time.monotonic() - t:.0f}s", flush=True)
for i, x in enumerate(lines):
    t = time.monotonic(); a, sr = say(x)
    sf.write(out / f"{m}-line{i + 1}.wav", np.asarray(a, dtype=np.float32).reshape(-1), sr)
    print(f"{m} line {i + 1}: {len(np.asarray(a).reshape(-1)) / sr:.1f}s of speech in {time.monotonic() - t:.1f}s", flush=True)
