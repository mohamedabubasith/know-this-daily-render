"""Kayal (Maya 2 Native, Apache-2.0) on CPU with the release's plain-PyTorch reference decoder: no CUDA, no Triton.
python kayal_cpu.py LINES_FILE OUT_WAV [N_LINES]"""
import os, sys, time
import numpy as np, soundfile as sf, torch
MAYA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maya")
for p in (MAYA, MAYA + "/scripts"):
    sys.path.insert(0, p)
from maya3 import hub
from maya3.prompt import load_named_voices, VoiceRegistry, DEFAULT_BUILDER, MODES
from maya3.text import normalise_text
from tts.data.packing_v2 import PackerV2
from tts.model.load_s3 import load_model_for_eval
from transformers import MimiModel
import s2_serve_controls as S

torch.set_num_threads(os.cpu_count() or 4)
dev, dt = "cpu", torch.float32
lines = open(sys.argv[1]).read().splitlines()[: int(sys.argv[3]) if len(sys.argv) > 3 else None]
t0 = time.monotonic()
r = hub.resolve("maya-research/maya2-native", include_model_config=True)
model, _ = load_model_for_eval(r["ckpt"], device=dev, dtype=dt, cfg={"model": {"backbone": r["backbone_dir"], "attn": "sdpa"}, "data": {"max_tokens": 8192}},
                               config=r.get("model_config"), amortize_frac=1.0, require_anchor=True, verbose=False)
model.eval(); model.depth.float()
mimi = MimiModel.from_pretrained(r["mimi_dir"]).eval()
packer = PackerV2(model.backbone.tokenizer, model.backbone.token_ids, max_tokens=8192)
prior = S.load_prior(os.path.join(MAYA, "configs/text_frames_prior.json"))
reg = VoiceRegistry(); load_named_voices(reg, r["voices_json"]); v = reg.get("Kayal")
use_icl, use_mem = MODES[v.mode]
refs = np.asarray(v.ecapa, np.float32).reshape(1, 192) if v.ecapa is not None else np.zeros((1, 192), np.float32)
with torch.inference_mode():
    mem = model.depth.spk_memory(torch.as_tensor(refs)[None], "ecapa", null_mask=torch.tensor([not use_mem]))
print(f"Kayal ({v.mode}) loaded in {time.monotonic() - t0:.0f}s", flush=True)
SR, parts = 24000, []
for i, line in enumerate(lines):
    t = time.monotonic()
    text = normalise_text(line, "ta")
    ex = (v.builder or DEFAULT_BUILDER).example(packer, v, text, "ta")
    with torch.inference_mode():
        prompt, _ = S.prompt_from_example(ex, model, dev, dt, 32)
        ef, er = S.expected_frames(prior, "ta", len(text))
        sess = S.ServeSession(model, mem, torch.ones(1, 1, dtype=torch.bool), q_serve=32, temp=0.7, top_k=64, device=dev)
        torch.manual_seed(1)
        codes, reason, _ = sess.speak(prompt.to(dt), cap=int(2.0 * (ef + er) + 40), stop="controlled", min_frames=max(4, int(0.5 * ef)))
        w = mimi.decode(codes[None].long())[0][0, 0].float().numpy()
    parts += [w, np.zeros(int(SR * 0.45), np.float32)]
    print(f"line {i + 1}: {len(w) / SR:.1f}s of speech in {time.monotonic() - t:.0f}s ({reason})", flush=True)
a = np.concatenate(parts); a = 0.9 * a / max(1e-6, np.abs(a).max())
sf.write(sys.argv[2], a, SR)
print("wrote", sys.argv[2], f"{len(a) / SR:.1f}s")
