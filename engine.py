"""Local voice cloning engine built on Chatterbox (Resemble AI, MIT license).

Voices live in voices/<name>/:
    samples/*.wav      raw recordings / uploads
    reference.wav      cleaned clip used to clone the voice
    voice.json         name, labels, description, language
"""
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import torch
import torchaudio

ROOT = Path(__file__).parent
VOICES_DIR = ROOT / "voices"
OUTPUT_DIR = ROOT / "outputs"
VOICES_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# On Apple Silicon the CPU is steadier than MPS for this model (MPS speed varies a lot run to run).
# Override with MYVOICE_DEVICE=mps (or cuda on an NVIDIA machine).
DEVICE = os.environ.get("MYVOICE_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
MAX_REFERENCE_SECONDS = 30
MAX_CHUNK_CHARS = 280

_models = {}


def slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
    if not slug:
        raise ValueError("Voice name is empty")
    return slug


# ---------------------------------------------------------------- voices

def _run_ffmpeg(args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def clean_sample(src: Path, dst: Path):
    """Mono 24 kHz, remove rumble, trim leading/trailing silence, normalise loudness."""
    filters = ",".join([
        "highpass=f=70",
        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1",
        "areverse",
        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1",
        "areverse",
        "loudnorm=I=-18:TP=-2:LRA=11",
    ])
    _run_ffmpeg(["-i", str(src), "-ac", "1", "-ar", "24000", "-af", filters, str(dst)])


def save_voice(name, sample_paths, labels=None, description="", language="en"):
    """Create/overwrite a voice from one or more audio files. Returns the voice dir."""
    if not sample_paths:
        raise ValueError("Add at least one recording or audio file")
    vdir = VOICES_DIR / slugify(name)
    samples_dir = vdir / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    cleaned = []
    for i, src in enumerate(sample_paths):
        src = Path(src)
        raw = samples_dir / f"sample_{int(time.time())}_{i}{src.suffix or '.wav'}"
        shutil.copy(src, raw)
        out = vdir / f"_clean_{i}.wav"
        clean_sample(raw, out)
        cleaned.append(out)

    # Concatenate the cleaned samples (with a short gap) into one reference clip.
    wavs = []
    for p in cleaned:
        w, sr = torchaudio.load(str(p))
        wavs += [w, torch.zeros(1, int(0.3 * sr))]
        p.unlink()
    ref = torch.cat(wavs, dim=1)[:, : MAX_REFERENCE_SECONDS * 24000]
    torchaudio.save(str(vdir / "reference.wav"), ref, 24000)

    meta = {
        "name": name.strip(),
        "labels": labels or {},
        "description": description,
        "language": language,
        "reference_seconds": round(ref.shape[1] / 24000, 1),
        "created": time.strftime("%Y-%m-%d %H:%M"),
    }
    (vdir / "voice.json").write_text(json.dumps(meta, indent=2))
    for old in vdir.glob("conds_*.pt"):  # invalidate cached voice embeddings
        old.unlink()
    return vdir


def list_voices():
    out = []
    for d in sorted(VOICES_DIR.iterdir()):
        if (d / "voice.json").exists() and (d / "reference.wav").exists():
            out.append(json.loads((d / "voice.json").read_text()) | {"id": d.name})
    return out


def voice_dir(name) -> Path:
    vdir = VOICES_DIR / slugify(name)
    if not (vdir / "reference.wav").exists():
        raise ValueError(f"Voice '{name}' not found. Create it first.")
    return vdir


def delete_voice(name):
    shutil.rmtree(voice_dir(name))


# ---------------------------------------------------------------- models

def get_model(language="en"):
    """English uses the original Chatterbox model; other languages use the multilingual one."""
    key = "en" if language == "en" else "mtl"
    if key not in _models:
        if key == "en":
            from chatterbox.tts import ChatterboxTTS
            _models[key] = ChatterboxTTS.from_pretrained(device=DEVICE)
        else:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            _models[key] = ChatterboxMultilingualTTS.from_pretrained(device=torch.device(DEVICE))
    return _models[key]


def supported_languages():
    from chatterbox.mtl_tts import SUPPORTED_LANGUAGES
    return SUPPORTED_LANGUAGES


# ---------------------------------------------------------------- text

def split_text(text, max_chars=MAX_CHUNK_CHARS):
    """Split into chunks of whole sentences. Yields (chunk, pause_after_seconds)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for p_i, para in enumerate(paragraphs):
        sentences = re.split(r"(?<=[.!?।])\s+", " ".join(para.split()))
        chunks, cur = [], ""
        for s in sentences:
            while len(s) > max_chars:  # very long sentence: break at a comma or space
                cut = max(s.rfind(",", 0, max_chars), s.rfind(" ", 0, max_chars))
                cut = cut if cut > 0 else max_chars
                if cur:
                    chunks.append(cur)
                    cur = ""
                chunks.append(s[: cut + 1].strip())
                s = s[cut + 1:].strip()
            if cur and len(cur) + 1 + len(s) > max_chars:
                chunks.append(cur)
                cur = s
            else:
                cur = f"{cur} {s}".strip()
        if cur:
            chunks.append(cur)
        for c_i, c in enumerate(chunks):
            last_in_para = c_i == len(chunks) - 1
            yield c, (0.7 if last_in_para and p_i < len(paragraphs) - 1 else 0.25)


def parse_script(text, default_voice):
    """Podcast scripts: lines like 'Ramesh: hello' switch to that saved voice.

    Returns [(voice_name, text_block), ...]. Lines without a known speaker
    continue with the current speaker.
    """
    known = {v["id"].lower(): v["id"] for v in list_voices()}
    known |= {v["name"].lower(): v["id"] for v in list_voices()}
    segments, voice, buf = [], default_voice, []
    for line in text.splitlines():
        m = re.match(r"^\s*\[?([A-Za-z0-9_ -]{1,40})\]?\s*:\s*(.*)$", line)
        if m and m.group(1).strip().lower() in known:
            if any(b.strip() for b in buf):
                segments.append((voice, "\n".join(buf).strip()))
            voice, buf = known[m.group(1).strip().lower()], [m.group(2)]
        else:
            buf.append(line)
    if any(b.strip() for b in buf):
        segments.append((voice, "\n".join(buf).strip()))
    return segments


# ---------------------------------------------------------------- synthesis

def _prepare(model, vdir, exaggeration):
    """Compute (or load cached) voice conditioning so repeat runs are fast."""
    cache = vdir / f"conds_{type(model).__name__}_{exaggeration:.2f}.pt"
    if cache.exists():
        import importlib
        Conditionals = importlib.import_module(type(model).__module__).Conditionals
        model.conds = Conditionals.load(cache, map_location="cpu").to(model.device)
    else:
        model.prepare_conditionals(str(vdir / "reference.wav"), exaggeration=exaggeration)
        model.conds.save(cache)


def speak(text, voice, language=None, exaggeration=0.5, cfg_weight=0.5,
          temperature=0.8, seed=42, out_name=None, progress=None):
    """Generate speech for any length of text. Returns (wav_path, mp3_path)."""
    segments = parse_script(text, voice)
    if not segments:
        raise ValueError("No text to speak")

    pieces, sr = [], None
    jobs = [(v, chunk, pause) for v, block in segments for chunk, pause in split_text(block)]
    current = None
    for i, (v, chunk, pause) in enumerate(jobs):
        vdir = voice_dir(v)
        lang = language or json.loads((vdir / "voice.json").read_text()).get("language", "en")
        model = get_model(lang)
        if current != (v, lang):
            _prepare(model, vdir, exaggeration)
            current = (v, lang)
        if progress:
            progress(i / len(jobs), f"Chunk {i + 1}/{len(jobs)} ({v})")
        if seed is not None:
            torch.manual_seed(seed + i)
        kwargs = dict(exaggeration=exaggeration, cfg_weight=cfg_weight, temperature=temperature)
        if lang != "en":
            kwargs["language_id"] = lang
        wav = model.generate(chunk, **kwargs).cpu()
        sr = model.sr
        pieces += [wav, torch.zeros(1, int(pause * sr))]

    audio = torch.cat(pieces[:-1], dim=1)
    stem = out_name or f"{slugify(voice)}_{time.strftime('%Y%m%d_%H%M%S')}"
    wav_path = OUTPUT_DIR / f"{stem}.wav"
    mp3_path = OUTPUT_DIR / f"{stem}.mp3"
    torchaudio.save(str(wav_path), audio, sr)
    _run_ffmpeg(["-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "192k", str(mp3_path)])
    if progress:
        progress(1.0, "Done")
    return wav_path, mp3_path
