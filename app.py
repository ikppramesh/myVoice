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

LANGS = {"en": "English"} | {k: v for k, v in sorted(engine.supported_languages().items()) if k != "en"}
LANG_CHOICES = [(f"{v} ({k})", k) for k, v in LANGS.items()]


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


def preview(name, language):
    vid = engine.slugify(name or "")
    text = f"Hi, this is {name}. This is a preview of my cloned voice, generated entirely on my own computer."
    wav, _ = engine.speak(text, vid, language=language, out_name=f"{vid}_preview")
    return str(wav)


# ------------------------------------------------------------ speak tab

def generate(text, voice, language, exaggeration, cfg_weight, temperature, seed, progress=gr.Progress()):
    if not voice:
        raise gr.Error("Pick a voice (create one first).")
    if not text.strip():
        raise gr.Error("Type something to say.")
    wav, mp3 = engine.speak(text, voice, language=language or None, exaggeration=exaggeration,
                            cfg_weight=cfg_weight, temperature=temperature,
                            seed=int(seed) if seed is not None and seed >= 0 else None, progress=progress)
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

    with gr.Tab("2 · Speak / Podcast"):
        with gr.Row():
            with gr.Column(scale=3):
                text = gr.Textbox(lines=14, label="Text or podcast script",
                                  placeholder="Paste any length of text.\n\nFor multi-voice podcasts, start lines "
                                              "with a saved voice name:\nRamesh: Welcome to the show!\nGuest: Thanks "
                                              "for having me.")
            with gr.Column(scale=2):
                voice = gr.Dropdown(voice_names(), value=(voice_names() or [None])[0], label="Voice")
                lang_override = gr.Dropdown([("Use voice's language", "")] + LANG_CHOICES, value="",
                                            label="Language")
                exaggeration = gr.Slider(0.25, 2.0, 0.5, step=0.05, label="Expressiveness",
                                         info="Higher = more emotion/energy (try 0.7 for lively podcasts)")
                cfg = gr.Slider(0.0, 1.0, 0.5, step=0.05, label="Pace / guidance",
                                info="Lower = slower, more deliberate delivery")
                temp = gr.Slider(0.05, 1.5, 0.8, step=0.05, label="Variation (temperature)")
                seed = gr.Number(42, label="Seed (-1 = random)", precision=0)
                go = gr.Button("🔊 Generate", variant="primary")
        out_audio = gr.Audio(label="Result", interactive=False)
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
    go.click(generate, [text, voice, lang_override, exaggeration, cfg, temp, seed], [out_audio, out_files])
    del_btn.click(remove, del_voice, [del_voice, table]).then(
        lambda: gr.update(choices=voice_names()), None, voice)

if __name__ == "__main__":
    demo.queue().launch(server_name="127.0.0.1", inbrowser=True)
