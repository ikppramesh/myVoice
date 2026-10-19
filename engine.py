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

# Indian languages are generated with IndicF5 (AI4Bharat), installed in its own venv.
INDIC_PYTHON = ROOT / ".venv-indic" / "bin" / "python"
INDIC_LANGS = {
    "te": "Telugu", "hi": "Hindi", "ta": "Tamil", "kn": "Kannada", "ml": "Malayalam", "mr": "Marathi",
    "bn": "Bengali", "gu": "Gujarati", "pa": "Punjabi", "or": "Odia", "as": "Assamese",
}
INDIC_MAX_REF_SECONDS = 14  # IndicF5 only uses ~15 s of reference; the transcript must match it exactly
# One sentence per language to read aloud; the text doubles as the reference transcript.
INDIC_SCRIPTS = {
    "te": "నమస్కారం! ఈ రోజు మనం ఒక ఆసక్తికరమైన విషయం గురించి మాట్లాడుకుందాం. మీరు చివరి వరకు వినండి.",
    "hi": "नमस्ते! आज हम एक बहुत ही दिलचस्प विषय के बारे में बात करेंगे। आप अंत तक ज़रूर सुनिए।",
    "ta": "வணக்கம்! இன்று நாம் ஒரு சுவாரஸ்யமான விஷயத்தைப் பற்றிப் பேசப் போகிறோம். கடைசி வரை கேளுங்கள்.",
    "kn": "ನಮಸ್ಕಾರ! ಇಂದು ನಾವು ಒಂದು ಆಸಕ್ತಿದಾಯಕ ವಿಷಯದ ಬಗ್ಗೆ ಮಾತನಾಡೋಣ. ಕೊನೆಯವರೆಗೂ ಕೇಳಿ.",
    "ml": "നമസ്കാരം! ഇന്ന് നമ്മൾ ഒരു രസകരമായ വിഷയത്തെക്കുറിച്ച് സംസാരിക്കാം. അവസാനം വരെ കേൾക്കൂ.",
    "mr": "नमस्कार! आज आपण एका मनोरंजक विषयावर बोलूया. शेवटपर्यंत नक्की ऐका.",
    "bn": "নমস্কার! আজ আমরা একটি মজার বিষয় নিয়ে কথা বলব। শেষ পর্যন্ত শুনুন।",
    "gu": "નમસ્તે! આજે આપણે એક રસપ્રદ વિષય વિશે વાત કરીશું. અંત સુધી જરૂર સાંભળજો.",
    "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਅੱਜ ਅਸੀਂ ਇੱਕ ਦਿਲਚਸਪ ਵਿਸ਼ੇ ਬਾਰੇ ਗੱਲ ਕਰਾਂਗੇ। ਅੰਤ ਤੱਕ ਜ਼ਰੂਰ ਸੁਣੋ।",
    "or": "ନମସ୍କାର! ଆଜି ଆମେ ଗୋଟିଏ ମଜାଦାର ବିଷୟରେ କଥା ହେବା। ଶେଷ ପର୍ଯ୍ୟନ୍ତ ଶୁଣନ୍ତୁ।",
    "as": "নমস্কাৰ! আজি আমি এটা আমোদজনক বিষয়ৰ বিষয়ে কথা পাতিম। শেষলৈকে শুনিব।",
}

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


def save_indic_reference(name, lang, audio_path, transcript):
    """Store a short clip of the voice speaking an Indian language, plus exactly what was said."""
    if lang not in INDIC_LANGS:
        raise ValueError(f"Unsupported Indian language: {lang}")
    if not transcript or not transcript.strip():
        raise ValueError("Type exactly what was said in the recording")
    idir = voice_dir(name) / "indic"
    idir.mkdir(exist_ok=True)
    tmp = idir / f"_{lang}_full.wav"
    clean_sample(Path(audio_path), tmp)
    seconds = torchaudio.info(str(tmp)).num_frames / 24000
    if seconds > INDIC_MAX_REF_SECONDS:
        tmp.unlink()
        raise ValueError(f"Recording is {seconds:.0f}s; keep it under {INDIC_MAX_REF_SECONDS}s "
                         "(read just the one sentence) so it matches the transcript")
    tmp.rename(idir / f"{lang}.wav")
    (idir / f"{lang}.txt").write_text(transcript.strip())
    return idir / f"{lang}.wav"


def indic_references(name):
    idir = VOICES_DIR / slugify(name) / "indic"
    return sorted(p.stem for p in idir.glob("*.wav")) if idir.exists() else []


def _indic_reference(vdir, lang):
    """Best reference for an Indian language: same language > any Indian language > main clip (auto-transcribed)."""
    idir = vdir / "indic"
    for cand in [idir / f"{lang}.wav", *sorted(idir.glob("*.wav"))] if idir.exists() else []:
        if cand.exists():
            return cand, cand.with_suffix(".txt").read_text()
    clip = vdir / "reference_short.wav"
    if not clip.exists() or clip.stat().st_mtime < (vdir / "reference.wav").stat().st_mtime:
        _run_ffmpeg(["-i", str(vdir / "reference.wav"), "-t", "12", str(clip)])
        clip.with_suffix(".txt").unlink(missing_ok=True)
    transcript = clip.with_suffix(".txt")
    # Empty transcript -> the worker transcribes it with Whisper once and reports it back (REFTEXT).
    return clip, transcript.read_text() if transcript.exists() else ""


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


# ---------------------------------------------------------------- translation

FLORES = {"te": "tel_Telu", "hi": "hin_Deva", "ta": "tam_Taml", "kn": "kan_Knda", "ml": "mal_Mlym",
          "mr": "mar_Deva", "bn": "ben_Beng", "gu": "guj_Gujr", "pa": "pan_Guru", "or": "ory_Orya",
          "as": "asm_Beng"}


def needs_translation(text):
    """True when the text is mostly Latin letters (i.e. English, not already Telugu/Hindi...)."""
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isascii() for c in letters) / len(letters) > 0.5


def translate(text, lang):
    """Translate English text to an Indian language, keeping paragraphs and 'Speaker:' tags.

    Returns (translated_text, model_name).
    """
    if lang not in FLORES:
        raise ValueError(f"Translation is available for Indian languages only, not '{lang}'")
    if not INDIC_PYTHON.exists():
        raise RuntimeError("Indian-language tools not installed (.venv-indic missing). See README.")
    known = {v["id"].lower() for v in list_voices()} | {v["name"].lower() for v in list_voices()}

    # Each line -> (speaker prefix to keep, [sentences to translate])
    layout, sentences = [], []
    for line in text.splitlines():
        prefix, body = "", line.strip()
        m = re.match(r"^\s*(\[?[A-Za-z0-9_ -]{1,40}\]?\s*:)\s*(.*)$", line)
        if m and m.group(1).strip("[]: ").lower() in known:
            prefix, body = m.group(1) + " ", m.group(2)
        parts = [s for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()] if needs_translation(body) else []
        layout.append((prefix, body, len(sentences), len(parts)))
        sentences += parts
    if not sentences:
        return text, "none (already translated)"

    work = OUTPUT_DIR / f"_tr_{os.getpid()}_{time.time_ns()}"
    Path(f"{work}.json").write_text(json.dumps(
        {"tgt": FLORES[lang], "sentences": sentences, "out": f"{work}.out.json"}, ensure_ascii=False))
    proc = subprocess.run([str(INDIC_PYTHON), str(ROOT / "translate_worker.py"), f"{work}.json"],
                          capture_output=True, text=True)
    Path(f"{work}.json").unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError("Translation failed:\n" + proc.stderr[-2000:])
    result = json.loads(Path(f"{work}.out.json").read_text())
    Path(f"{work}.out.json").unlink()

    lines = []
    for prefix, body, start, n in layout:
        lines.append(prefix + (" ".join(result["sentences"][start:start + n]) if n else body))
    return "\n".join(lines), result["model"]


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


def _speak_chatterbox(chunks, vdir, lang, exaggeration, cfg_weight, temperature, seed, tick):
    model = get_model(lang)
    _prepare(model, vdir, exaggeration)
    pieces = []
    for text, pause in chunks:
        tick()
        if seed is not None:
            torch.manual_seed(seed + len(pieces))
        kwargs = dict(exaggeration=exaggeration, cfg_weight=cfg_weight, temperature=temperature)
        if lang != "en":
            kwargs["language_id"] = lang
        pieces += [model.generate(text, **kwargs).cpu(), torch.zeros(1, int(pause * model.sr))]
    return pieces, model.sr


def _speak_indic(chunks, vdir, lang, tick):
    if not INDIC_PYTHON.exists():
        raise RuntimeError("Indian-language engine not installed (.venv-indic missing). See README.")
    ref_audio, ref_text = _indic_reference(vdir, lang)
    work = OUTPUT_DIR / f"_indic_{os.getpid()}_{time.time_ns()}"
    job = {"ref_audio": str(ref_audio), "ref_text": ref_text, "chunks": chunks, "out": f"{work}.wav"}
    Path(f"{work}.json").write_text(json.dumps(job, ensure_ascii=False))
    # stderr goes to a file: a chatty worker filling an unread stderr pipe would deadlock us.
    with open(f"{work}.log", "w+") as log:
        proc = subprocess.Popen([str(INDIC_PYTHON), str(ROOT / "indic_worker.py"), f"{work}.json"],
                                stdout=subprocess.PIPE, stderr=log, text=True)
        seen = set()
        for line in proc.stdout:
            parts = line.split()
            if parts[:1] == ["REFTEXT"]:
                Path(ref_audio).with_suffix(".txt").write_text(json.loads(line[len("REFTEXT "):]))
            elif parts[:1] == ["PROGRESS"] and int(parts[1]) < len(chunks) and parts[1] not in seen:
                seen.add(parts[1])
                tick()
        proc.wait()
        log.seek(0)
        err = log.read()
    Path(f"{work}.log").unlink(missing_ok=True)
    Path(f"{work}.json").unlink(missing_ok=True)
    if proc.wait() != 0:
        if "gated repo" in err or "restricted" in err:
            raise RuntimeError("IndicF5 access not granted yet: accept the terms at "
                               "https://huggingface.co/ai4bharat/IndicF5 (logged in as your HF account)")
        raise RuntimeError("IndicF5 failed:\n" + err[-2000:])
    wav, sr = torchaudio.load(f"{work}.wav")
    Path(f"{work}.wav").unlink()
    return [wav, torch.zeros(1, int(chunks[-1][1] * sr))], sr


def speak(text, voice, language=None, exaggeration=0.5, cfg_weight=0.5,
          temperature=0.8, seed=42, out_name=None, progress=None):
    """Generate speech for any length of text. Returns (wav_path, mp3_path).

    English and the Chatterbox multilingual languages use Chatterbox; Indian
    languages (INDIC_LANGS) use IndicF5.
    """
    segments = parse_script(text, voice)
    if not segments:
        raise ValueError("No text to speak")

    plan = [(v, list(split_text(block))) for v, block in segments]
    total, done = sum(len(c) for _, c in plan), [0]

    def tick():
        if progress:
            progress(done[0] / total, f"Chunk {done[0] + 1}/{total}")
        done[0] += 1

    pieces, out_sr = [], 24000
    for v, chunks in plan:
        vdir = voice_dir(v)
        lang = language or json.loads((vdir / "voice.json").read_text()).get("language", "en")
        if lang in INDIC_LANGS:
            seg, sr = _speak_indic(chunks, vdir, lang, tick)
        else:
            seg, sr = _speak_chatterbox(chunks, vdir, lang, exaggeration, cfg_weight, temperature, seed, tick)
        if sr != out_sr:
            seg = [torchaudio.functional.resample(p, sr, out_sr) for p in seg]
        pieces += seg

    audio = torch.cat(pieces[:-1], dim=1)
    stem = out_name or f"{slugify(voice)}_{time.strftime('%Y%m%d_%H%M%S')}"
    wav_path = OUTPUT_DIR / f"{stem}.wav"
    mp3_path = OUTPUT_DIR / f"{stem}.mp3"
    torchaudio.save(str(wav_path), audio, out_sr)
    _run_ffmpeg(["-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "192k", str(mp3_path)])
    if progress:
        progress(1.0, "Done")
    return wav_path, mp3_path
