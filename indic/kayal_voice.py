"""Kayal (Maya 2 Native, Apache-2.0) on CPU: python kayal_voice.py UNITS_JSON MAYA_SRC

Loads the model at once (the runner starts this while Claude still writes the script), then waits for UNITS_JSON:
[{"text": one sentence, "out": WAV path}, ...]. Every sentence becomes a 24 kHz 16-bit mono WAV; part.py joins them
into lines with the narrator's pauses. Writes UNITS_JSON.done when finished, UNITS_JSON.failed (the error) if not.
Uses the release's plain-PyTorch reference decoder (scripts/s2_serve_controls.ServeSession): no CUDA, no Triton."""
import json, os, sys, time, traceback
from pathlib import Path

units_path, src = Path(sys.argv[1]), Path(sys.argv[2])
try:
    import numpy as np, soundfile as sf, torch
    for p in (src, src / "scripts"):
        sys.path.insert(0, str(p))
    from maya3 import hub
    from maya3.prompt import load_named_voices, VoiceRegistry, DEFAULT_BUILDER, MODES
    from maya3.text import normalise_text
    from tts.data.packing_v2 import PackerV2
    from tts.model.load_s3 import load_model_for_eval
    from transformers import MimiModel
    import s2_serve_controls as S

    torch.set_num_threads(os.cpu_count() or 4)
    dev, dt = "cpu", torch.float32
    t0 = time.monotonic()
    r = hub.resolve("maya-research/maya2-native", include_model_config=True)
    model, _ = load_model_for_eval(r["ckpt"], device=dev, dtype=dt, config=r.get("model_config"), amortize_frac=1.0,
                                   cfg={"model": {"backbone": r["backbone_dir"], "attn": "sdpa"}, "data": {"max_tokens": 8192}},
                                   require_anchor=True, verbose=False)
    model.eval(); model.depth.float()
    mimi = MimiModel.from_pretrained(r["mimi_dir"]).eval()
    packer = PackerV2(model.backbone.tokenizer, model.backbone.token_ids, max_tokens=8192)
    prior = S.load_prior(str(src / "configs/text_frames_prior.json"))
    reg = VoiceRegistry(); load_named_voices(reg, r["voices_json"]); v = reg.get("Kayal")
    use_icl, use_mem = MODES[v.mode]
    refs = np.asarray(v.ecapa, np.float32).reshape(1, 192) if v.ecapa is not None else np.zeros((1, 192), np.float32)
    with torch.inference_mode():
        mem = model.depth.spk_memory(torch.as_tensor(refs)[None], "ecapa", null_mask=torch.tensor([not use_mem]))
    print(f"Kayal loaded in {time.monotonic() - t0:.0f}s", flush=True)

    end = time.monotonic() + 1800
    while not units_path.exists():
        if time.monotonic() > end:
            raise TimeoutError("no sentences arrived in 30 minutes")
        time.sleep(1)
    for i, u in enumerate(json.loads(units_path.read_text())):
        t = time.monotonic()
        text = normalise_text(u["text"], "ta")
        with torch.inference_mode():
            prompt, _ = S.prompt_from_example((v.builder or DEFAULT_BUILDER).example(packer, v, text, "ta"), model, dev, dt, 32)
            ef, er = S.expected_frames(prior, "ta", len(text))
            sess = S.ServeSession(model, mem, torch.ones(1, 1, dtype=torch.bool), q_serve=32, temp=0.7, top_k=64, device=dev)
            torch.manual_seed(1000 + i)
            codes, reason, _ = sess.speak(prompt.to(dt), cap=int(2.0 * (ef + er) + 40), stop="controlled", min_frames=max(4, int(0.5 * ef)))
            w = mimi.decode(codes[None].long())[0][0, 0].float().numpy()
        Path(u["out"]).parent.mkdir(parents=True, exist_ok=True)
        sf.write(u["out"], np.clip(w, -1, 1), 24000, subtype="PCM_16")
        print(f"  {len(u['text'])} letters: {len(w) / 24000:.1f}s in {time.monotonic() - t:.0f}s ({reason})", flush=True)
    Path(str(units_path) + ".done").write_text("ok")
except Exception:
    Path(str(units_path) + ".failed").write_text(traceback.format_exc()[-3000:])
    raise
