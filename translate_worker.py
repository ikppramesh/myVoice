"""English -> Indian language translation (runs inside .venv-indic, called by engine.py).

Usage: .venv-indic/bin/python translate_worker.py job.json
job.json: {"tgt": "tel_Telu", "sentences": [...], "out": path}
Uses AI4Bharat IndicTrans2 when this machine has access (best quality), else Meta NLLB-200.
Writes {"model": name, "sentences": [...]} to "out".
"""
import json
import sys

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

INDICTRANS = "ai4bharat/indictrans2-en-indic-1B"
NLLB = "facebook/nllb-200-distilled-600M"
BATCH = 8


def load_indictrans():
    from IndicTransToolkit.processor import IndicProcessor
    tok = AutoTokenizer.from_pretrained(INDICTRANS, trust_remote_code=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(INDICTRANS, trust_remote_code=True).eval()
    ip = IndicProcessor(inference=True)

    def run(sents, tgt):
        batch = ip.preprocess_batch(sents, src_lang="eng_Latn", tgt_lang=tgt)
        x = tok(batch, truncation=True, padding="longest", return_tensors="pt", return_attention_mask=True)
        out = model.generate(**x, use_cache=False, min_length=0, max_length=256, num_beams=5)
        dec = tok.batch_decode(out, skip_special_tokens=True, clean_up_tokenization_spaces=True)
        return ip.postprocess_batch(dec, lang=tgt)
    return run


def load_nllb():
    tok = AutoTokenizer.from_pretrained(NLLB, src_lang="eng_Latn")
    model = AutoModelForSeq2SeqLM.from_pretrained(NLLB).eval()

    def run(sents, tgt):
        x = tok(sents, return_tensors="pt", padding=True, truncation=True)
        out = model.generate(**x, forced_bos_token_id=tok.convert_tokens_to_ids(tgt), max_length=256, num_beams=4)
        return tok.batch_decode(out, skip_special_tokens=True)
    return run


def main():
    job = json.loads(open(sys.argv[1]).read())
    try:
        run, name = load_indictrans(), "IndicTrans2 (AI4Bharat)"
    except Exception as e:  # gated / not downloaded / incompatible -> fall back
        print(f"IndicTrans2 unavailable ({type(e).__name__}); using NLLB-200", file=sys.stderr)
        run, name = load_nllb(), "NLLB-200 (Meta)"
    sents, out = job["sentences"], []
    with torch.no_grad():
        for i in range(0, len(sents), BATCH):
            out += run(sents[i:i + BATCH], job["tgt"])
    json.dump({"model": name, "sentences": out}, open(job["out"], "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
