"""myVoice — local instant voice cloning studio.  Run:  ./run.sh   (opens http://127.0.0.1:7860)"""
import gradio as gr

import engine

READING_SCRIPT = """**Read these aloud in your natural speaking voice** (add each as a sample, or record them all in one take):

1. Hi, I'm recording this so I can have a digital version of my own voice. I'm speaking naturally, at my normal pace, the same way I would talk to a friend.

2. Welcome back to the show! Today we've got a really interesting topic. Honestly, I couldn't wait to share this with you — so let's dive right in.

3. The quick brown fox jumps over the lazy dog. She sells seashells by the seashore. How much wood would a woodchuck chuck?

4. Hmm, that's a good question. Well, I think the answer depends on what you really want. Is it speed? Quality? Or maybe a bit of both?

5. Thanks so much for listening. If you enjoyed this episode, share it with someone who'd love it too. See you next time, take care!

**Tips:** quiet room, mic 15–20 cm from your mouth, no music or echo. 30 seconds to 2 minutes total is plenty —
clean audio matters far more than length. Speak with the energy you want the clone to have."""

LANGS = ({"en": "English"} | dict(engine.INDIC_LANGS)
         | {k: v for k, v in sorted(engine.supported_languages().items()) if k not in ("en", *engine.INDIC_LANGS)})
LANG_CHOICES = [(f"{v} ({k})" + (" · Indian" if k in engine.INDIC_LANGS else ""), k) for k, v in LANGS.items()]
INDIC_CHOICES = [(f"{v} ({k})", k) for k, v in engine.INDIC_LANGS.items()]


def voice_names():
    return [v["id"] for v in engine.list_voices()]


def voices_table():
    return [[v["name"], v["id"], LANGS.get(v["language"], v["language"]),
             ", ".join(f"{k}: {val}" for k, val in v["labels"].items()),
             v["reference_seconds"], v["created"]] for v in engine.list_voices()]


# ------------------------------------------------------------ create tab

def add_sample(new, samples):
    if not new:
        gr.Warning("Record or upload something first.")
        return samples, None, sample_summary(samples)
    samples = samples + [new]
    return samples, None, sample_summary(samples)


def add_files(files, samples):
    samples = samples + [f if isinstance(f, str) else f.name for f in (files or [])]
    return samples, None, sample_summary(samples)


def sample_summary(samples):
    if not samples:
        return "_No samples yet._"
    return f"**{len(samples)} sample(s) ready:**\n" + "\n".join(f"- {s.split('/')[-1]}" for s in samples)


def parse_labels(rows):
    labels = {}
    for row in rows or []:
        if len(row) >= 2 and str(row[0]).strip() and str(row[1]).strip():
            labels[str(row[0]).strip()] = str(row[1]).strip()
    return labels


def save(name, language, description, labels_df, consent, samples):
    if not consent:
        raise gr.Error("Please confirm this is your own voice (or you have permission).")
    if not name or not name.strip():
        raise gr.Error("Give your voice a name.")
    if not samples:
        raise gr.Error("Add at least one sample in step 1.")
    rows = labels_df.values.tolist() if hasattr(labels_df, "values") else labels_df
    vdir = engine.save_voice(name, samples, parse_labels(rows), description, language)
    meta = (vdir / "voice.json").read_text()
    gr.Info(f"Voice '{name}' saved.")
    names = voice_names()
    return (str(vdir / "reference.wav"), f"Saved to `{vdir}`\n```json\n{meta}\n```", [],
            sample_summary([]), gr.update(choices=names, value=vdir.name), voices_table())


PREVIEW_TEXT = {
    "te": "నమస్కారం, ఇది నా స్వంత గొంతు. ఇది పూర్తిగా నా కంప్యూటర్‌లోనే తయారైంది.",
    "hi": "नमस्ते, यह मेरी अपनी आवाज़ है। यह पूरी तरह मेरे कंप्यूटर पर बनाई गई है।",
}


def preview(name, language):
    vid = engine.slugify(name or "")
    text = PREVIEW_TEXT.get(language) or (
        f"Hi, this is {name}. This is a preview of my cloned voice, generated entirely on my own computer.")
    wav, _ = engine.speak(text, vid, language=language, out_name=f"{vid}_preview")
    return str(wav)


def indic_status(name):
    try:
        have = engine.indic_references(name)
    except ValueError:
        have = []
    if not have:
        return ("_No Indian-language samples yet. Without one, your main recording is used "
                "(works, but with an English accent)._")
    return "**Saved Indian-language samples:** " + ", ".join(engine.INDIC_LANGS[l] for l in have)


def indic_script(lang):
    text = engine.INDIC_SCRIPTS.get(lang, "")
    return f"### Read this aloud (one sentence, under {engine.INDIC_MAX_REF_SECONDS} s):\n\n## {text}", text


def save_indic(name, lang, audio, transcript):
    if not audio:
        raise gr.Error("Record or upload the sentence first.")
    try:
        engine.voice_dir(name)
    except ValueError:
        raise gr.Error("Save the voice in Step 3 first, then add Indian-language samples.")
    try:
        engine.save_indic_reference(name, lang, audio, transcript)
    except ValueError as e:
        raise gr.Error(str(e))
    gr.Info(f"{engine.INDIC_LANGS[lang]} sample saved for '{name}'.")
    return None, indic_status(name)


# ------------------------------------------------------------ speak tab

def effective_lang(voice, override):
    if override:
        return override
    v = next((v for v in engine.list_voices() if v["id"] == voice), None)
    return v["language"] if v else "en"


def on_lang_change(voice, override):
    lang = effective_lang(voice, override)
    indic = lang in engine.INDIC_LANGS
    name = engine.INDIC_LANGS.get(lang, "")
    return (gr.update(visible=indic, label=f"{name} text — review & edit before generating"),
            gr.update(visible=indic, value=f"🌐 Translate to {name}" if indic else "🌐 Translate"))


def do_translate(text, voice, override, progress=gr.Progress()):
    lang = effective_lang(voice, override)
    if not text.strip():
        raise gr.Error("Type the English text first.")
    progress(0.1, "Translating… (first time downloads the translation model)")
    try:
        out, model = engine.translate(text, lang)
    except Exception as e:
        raise gr.Error(str(e))
    note = (f"✅ Translated to {engine.INDIC_LANGS[lang]} with {model}. **Review and fix the text below**, "
            "then press Generate and listen to the result.")
    return out, note, text


def prepare(text, translated, translated_from, voice, override, progress=gr.Progress()):
    """Step 1 of Generate: for Indian languages, translate if the English changed since last time."""
    if not voice:
        raise gr.Error("Pick a voice (create one first).")
    if not text.strip() and not (translated or "").strip():
        raise gr.Error("Type something to say.")
    lang = effective_lang(voice, override)
    if (lang in engine.INDIC_LANGS and engine.needs_translation(text)
            and (not translated.strip() or translated_from != text)):
        return do_translate(text, voice, override, progress)
    return translated, gr.update(), translated_from


def generate(text, translated, voice, override, exaggeration, cfg_weight, temperature, seed,
             progress=gr.Progress()):
    """Step 2 of Generate: speak the reviewed translation (Indian languages) or the original text."""
    lang = effective_lang(voice, override)
    to_speak = translated if lang in engine.INDIC_LANGS and translated.strip() else text
    try:
        wav, mp3 = engine.speak(to_speak, voice, language=lang, exaggeration=exaggeration,
                                cfg_weight=cfg_weight, temperature=temperature,
                                seed=int(seed) if seed is not None and seed >= 0 else None, progress=progress)
    except Exception as e:
        raise gr.Error(str(e), duration=None)
    return str(wav), [str(wav), str(mp3)]


def remove(voice):
    if voice:
        engine.delete_voice(voice)
        gr.Info(f"Deleted '{voice}'.")
    return gr.update(choices=voice_names(), value=None), voices_table()


# ------------------------------------------------------------ UI

with gr.Blocks(title="myVoice") as demo:
    gr.Markdown(f"# 🎙️ myVoice — local voice cloning\nRuns 100% on this machine (`{engine.DEVICE}`). "
                "Nothing is uploaded anywhere.")
    samples = gr.State([])

    with gr.Tab("1 · Create voice"):
        with gr.Row():
            with gr.Column(scale=3):
                gr.Markdown("### Step 1 — Record or upload audio")
                gr.Markdown(READING_SCRIPT)
            with gr.Column(scale=2):
                mic = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Record (or drop a file)")
                add_btn = gr.Button("➕ Add this sample", variant="secondary")
                files = gr.File(file_count="multiple", file_types=["audio", "video"],
                                label="…or upload existing recordings (wav, mp3, m4a, mp4…)")
                sample_list = gr.Markdown(sample_summary([]))
                clear_btn = gr.Button("Clear samples", size="sm")

        gr.Markdown("### Step 2 — Voice information")
        with gr.Row():
            name = gr.Textbox(label="Name", value="Ramesh")
            language = gr.Dropdown(LANG_CHOICES, value="en", label="Primary language")
        description = gr.Textbox(label="Description (optional)", placeholder="Warm, calm podcast voice")
        labels = gr.Dataframe(headers=["Label", "Value"], value=[["accent", ""], ["use case", "podcast"]],
                              col_count=(2, "fixed"), interactive=True, label="Labels")
        consent = gr.Checkbox(label="I confirm this is my own voice, or I have permission to clone it.")

        gr.Markdown("### Step 3 — Finish up")
        with gr.Row():
            save_btn = gr.Button("💾 Save voice", variant="primary")
            preview_btn = gr.Button("▶️ Preview voice")
        with gr.Row():
            ref_audio = gr.Audio(label="Cleaned reference clip", interactive=False)
            preview_audio = gr.Audio(label="Preview (cloned)", interactive=False)
        save_info = gr.Markdown()

        gr.Markdown("### Step 4 — Indian languages (Telugu, Hindi, Tamil…)\n"
                    "For a natural accent, record yourself reading **one short sentence in each language** you "
                    "want. Uses IndicF5 (AI4Bharat). If you upload instead, type exactly what you said.")
        with gr.Row():
            with gr.Column(scale=3):
                indic_lang = gr.Dropdown(INDIC_CHOICES, value="te", label="Language")
                indic_text_md = gr.Markdown(indic_script("te")[0])
                indic_transcript = gr.Textbox(value=indic_script("te")[1], label="Transcript (exactly what you said)")
            with gr.Column(scale=2):
                indic_audio = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Record sentence")
                indic_btn = gr.Button("💾 Save language sample", variant="primary")
                indic_info = gr.Markdown(indic_status("Ramesh"))

    with gr.Tab("2 · Speak / Podcast"):
        with gr.Row():
            with gr.Column(scale=3):
                text = gr.Textbox(lines=14, label="Text or podcast script",
                                  placeholder="Paste any length of text.\n\nFor multi-voice podcasts, start lines "
                                              "with a saved voice name:\nRamesh: Welcome to the show!\nGuest: Thanks "
                                              "for having me.")
                tr_note = gr.Markdown()
                translated = gr.Textbox(lines=10, visible=False, label="Translated text — review & edit")
                translated_from = gr.State("")
            with gr.Column(scale=2):
                voice = gr.Dropdown(voice_names(), value=(voice_names() or [None])[0], label="Voice")
                lang_override = gr.Dropdown([("Use voice's language", "")] + LANG_CHOICES, value="",
                                            label="Language",
                                            info="Indian languages use IndicF5; the sliders below apply to "
                                                 "the other languages only")
                exaggeration = gr.Slider(0.25, 2.0, 0.5, step=0.05, label="Expressiveness",
                                         info="Higher = more emotion/energy (try 0.7 for lively podcasts)")
                cfg = gr.Slider(0.0, 1.0, 0.5, step=0.05, label="Pace / guidance",
                                info="Lower = slower, more deliberate delivery")
                temp = gr.Slider(0.05, 1.5, 0.8, step=0.05, label="Variation (temperature)")
                seed = gr.Number(42, label="Seed (-1 = random)", precision=0)
                tr_btn = gr.Button("🌐 Translate", visible=False)
                go = gr.Button("🔊 Generate", variant="primary")
        out_audio = gr.Audio(label="Result — listen to review your voice", interactive=False)
        out_files = gr.File(label="Download (WAV / MP3)")

    with gr.Tab("My voices"):
        table = gr.Dataframe(voices_table(), headers=["Name", "ID", "Language", "Labels", "Ref (s)", "Created"],
                             interactive=False)
        with gr.Row():
            del_voice = gr.Dropdown(voice_names(), label="Voice to delete")
            del_btn = gr.Button("🗑️ Delete", variant="stop")

    add_btn.click(add_sample, [mic, samples], [samples, mic, sample_list])
    files.upload(add_files, [files, samples], [samples, files, sample_list])
    clear_btn.click(lambda: ([], sample_summary([])), None, [samples, sample_list])
    save_btn.click(save, [name, language, description, labels, consent, samples],
                   [ref_audio, save_info, samples, sample_list, voice, table])
    preview_btn.click(preview, [name, language], preview_audio)
    indic_lang.change(indic_script, indic_lang, [indic_text_md, indic_transcript])
    indic_btn.click(save_indic, [name, indic_lang, indic_audio, indic_transcript], [indic_audio, indic_info])
    name.change(indic_status, name, indic_info)
    lang_override.change(on_lang_change, [voice, lang_override], [translated, tr_btn])
    voice.change(on_lang_change, [voice, lang_override], [translated, tr_btn])
    tr_btn.click(do_translate, [text, voice, lang_override], [translated, tr_note, translated_from])
    go.click(prepare, [text, translated, translated_from, voice, lang_override],
             [translated, tr_note, translated_from]).success(
        generate, [text, translated, voice, lang_override, exaggeration, cfg, temp, seed], [out_audio, out_files])
    del_btn.click(remove, del_voice, [del_voice, table]).then(
        lambda: gr.update(choices=voice_names()), None, voice)

if __name__ == "__main__":
    demo.queue().launch(server_name="127.0.0.1", inbrowser=True)
