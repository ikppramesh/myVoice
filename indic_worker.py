"""IndicF5 worker (runs inside .venv-indic, called by engine.py).

Usage: .venv-indic/bin/python indic_worker.py job.json
job.json: {"ref_audio": path, "ref_text": str, "chunks": [[text, pause_s], ...], "out": path}
Prints "PROGRESS <done> <total>" lines while working and writes a 24 kHz mono WAV to "out".

The model is assembled from f5_tts parts and the repo's model.safetensors instead of
AutoModel.from_pretrained: IndicF5's remote code builds its sub-models inside __init__, which
breaks under recent transformers (meta-device init -> "Cannot copy out of meta tensor").
"""
import io
import json
import os
import sys

import numpy as np
import soundfile as sf
import torch
from f5_tts.infer.utils_infer import infer_process, load_model, load_vocoder, preprocess_ref_audio_text
from f5_tts.model import DiT
from huggingface_hub import hf_hub_download
from pydub import AudioSegment, silence
from safetensors.torch import load_file

REPO = "ai4bharat/IndicF5"
SR = 24000
# MPS was ~2x faster than CPU for IndicF5 on an M3 Pro; override with MYVOICE_INDIC_DEVICE=cpu
DEVICE = os.environ.get("MYVOICE_INDIC_DEVICE") or (
    "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")


def quiet(*_args, **_kwargs):
    pass


def load():
    weights = load_file(hf_hub_download(REPO, "model.safetensors"))

    def part(prefix):
        return {k[len(prefix):]: v for k, v in weights.items() if k.startswith(prefix)}

    vocoder = load_vocoder(vocoder_name="vocos", is_local=False, device=DEVICE)
    vocoder.load_state_dict(part("vocoder._orig_mod."))
    model = load_model(DiT, dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4),
                       mel_spec_type="vocos", vocab_file=hf_hub_download(REPO, "checkpoints/vocab.txt"),
                       device=DEVICE)
    model.load_state_dict(part("ema_model._orig_mod."))
    return model.eval(), vocoder.eval()


def bytes_per_char(text):
    return len(text.encode("utf-8")) / max(len(text), 1)


def synth(model, vocoder, ref_audio, ref_text, text):
    """Same post-processing as IndicF5's own forward(): drop long silences, normalise to -20 dBFS."""
    # f5_tts sizes the output from UTF-8 byte counts. Indic scripts use ~3 bytes/char vs 1 for an
    # English reference transcript, which would make speech ~3x too slow, so compensate via speed.
    speed = max(1.0, bytes_per_char(text) / bytes_per_char(ref_text))
    audio, _, _ = infer_process(ref_audio, ref_text, text, model, vocoder, mel_spec_type="vocos",
                                show_info=quiet, speed=speed, device=DEVICE)
    buf = io.BytesIO()
    sf.write(buf, audio, samplerate=SR, format="WAV")
    buf.seek(0)
    seg = AudioSegment.from_file(buf, format="wav")
    seg = sum(silence.split_on_silence(seg, min_silence_len=1000, silence_thresh=-50, keep_silence=500,
                                       seek_step=10), AudioSegment.silent(duration=0))
    seg = seg.apply_gain(-20.0 - seg.dBFS)
    return np.array(seg.get_array_of_samples()).astype(np.float32) / 32768.0


def main():
    job = json.loads(open(sys.argv[1]).read())
    chunks = job["chunks"]
    print(f"PROGRESS 0 {len(chunks)}", flush=True)
    model, vocoder = load()
    ref_audio, ref_text = preprocess_ref_audio_text(job["ref_audio"], job["ref_text"], show_info=quiet,
                                                    device=DEVICE)
    if not job["ref_text"]:
        print("REFTEXT " + json.dumps(ref_text, ensure_ascii=False), flush=True)
    pieces = []
    with torch.inference_mode():
        for i, (text, pause) in enumerate(chunks):
            print(f"PROGRESS {i} {len(chunks)}", flush=True)
            pieces += [synth(model, vocoder, ref_audio, ref_text, text), np.zeros(int(pause * SR), np.float32)]
    sf.write(job["out"], np.concatenate(pieces[:-1]), SR)
    print(f"PROGRESS {len(chunks)} {len(chunks)}", flush=True)


if __name__ == "__main__":
    main()
