"""One video clip from text with LTX-Video 2B distilled, on CPU only (a GitHub runner): times every step.

    python story/ltx_clip.py OUT.mp4 "prompt" [WIDTH HEIGHT FRAMES]

All weights download anonymously from Hugging Face (public, no account). The text reader (T5, 19 GB as stored) is
loaded alone in bf16, used once and freed before the video model loads, so 16 GB of memory is enough."""
import gc
import os
import sys
import time

import torch

T0 = time.monotonic()
def log(msg):
    print(f"[{(time.monotonic() - T0) / 60:5.1f} min] {msg}", flush=True)

out, prompt = sys.argv[1], sys.argv[2]
W, H, F = (int(x) for x in (sys.argv[3:6] if len(sys.argv) > 5 else (768, 448, 97)))
torch.set_num_threads(os.cpu_count() or 4)
DT = getattr(torch, os.environ.get("LTX_DTYPE", "bfloat16"))  # the runners' Xeons do bf16 in hardware (AMX)
NEG = "worst quality, inconsistent motion, blurry, jittery, distorted"
REPO = "Lightricks/LTX-Video-0.9.5"  # the diffusers layout: text reader, tokenizer, scheduler and configs
SINGLE = "https://huggingface.co/Lightricks/LTX-Video/blob/main/ltxv-2b-0.9.8-distilled.safetensors"

# 1. the prompt, read by T5 (then freed)
from transformers import T5EncoderModel, T5TokenizerFast
tok = T5TokenizerFast.from_pretrained(REPO, subfolder="tokenizer")
te = T5EncoderModel.from_pretrained(REPO, subfolder="text_encoder", torch_dtype=torch.bfloat16)
log("text reader loaded")
def enc(text):
    t = tok(text, padding="max_length", max_length=128, truncation=True, return_tensors="pt")
    with torch.no_grad():
        e = te(t.input_ids, attention_mask=t.attention_mask)[0]
    return e.to(DT), t.attention_mask
pe, pm = enc(prompt)
ne, nm = enc(NEG)
del te; gc.collect()
log("prompt read")

# 2. the video model (2B distilled) and its VAE, from the single file
from diffusers import AutoencoderKLLTXVideo, LTXConditionPipeline, LTXVideoTransformer3DModel
from diffusers.utils import export_to_video
tr = LTXVideoTransformer3DModel.from_single_file(SINGLE, torch_dtype=DT)
vae = AutoencoderKLLTXVideo.from_single_file(SINGLE, torch_dtype=DT)
pipe = LTXConditionPipeline.from_pretrained(REPO, transformer=tr, vae=vae, text_encoder=None, tokenizer=None, torch_dtype=DT)
log("video model loaded")

steps_t = []
def on_step(p, i, t, kw):
    steps_t.append(time.monotonic()); log(f"step {i + 1} done")
    return kw

with torch.no_grad():
    video = pipe(prompt_embeds=pe, prompt_attention_mask=pm, negative_prompt_embeds=ne, negative_prompt_attention_mask=nm,
                 width=W, height=H, num_frames=F, num_inference_steps=8,
                 timesteps=[1000, 993, 987, 981, 975, 909, 725, 0.03], guidance_scale=1.0,
                 decode_timestep=0.05, decode_noise_scale=0.025, generator=torch.Generator().manual_seed(7),
                 callback_on_step_end=on_step, output_type="pil").frames[0]
log("decoded")
export_to_video(video, out, fps=24)
d = [b - a for a, b in zip(steps_t, steps_t[1:])]
log(f"done: {W}x{H}, {F} frames ({F / 24:.1f} s); a step takes about {sum(d) / max(1, len(d)):.0f} s")
