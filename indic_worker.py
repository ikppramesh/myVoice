"""IndicF5 worker (runs inside .venv-indic, called by engine.py).

Usage: .venv-indic/bin/python indic_worker.py job.json
job.json: {"ref_audio": path, "ref_text": str, "chunks": [[text, pause_s], ...], "out": path}
Prints "PROGRESS <done> <total>" lines while working and writes a 24 kHz mono WAV to "out".
"""
import json
import sys

import numpy as np
import soundfile as sf
from transformers import AutoModel

SR = 24000


def main():
    job = json.loads(open(sys.argv[1]).read())
    model = AutoModel.from_pretrained("ai4bharat/IndicF5", trust_remote_code=True)
    chunks = job["chunks"]
    pieces = []
    for i, (text, pause) in enumerate(chunks):
        print(f"PROGRESS {i} {len(chunks)}", flush=True)
        audio = np.asarray(model(text, ref_audio_path=job["ref_audio"], ref_text=job["ref_text"]))
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        pieces += [audio.astype(np.float32).reshape(-1), np.zeros(int(pause * SR), dtype=np.float32)]
    sf.write(job["out"], np.concatenate(pieces[:-1]), SR)
    print(f"PROGRESS {len(chunks)} {len(chunks)}", flush=True)


if __name__ == "__main__":
    main()
