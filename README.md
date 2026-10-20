# myVoice — your own voice, cloned locally

Local "Instant Voice Clone" (like ElevenLabs) using the open-source **Chatterbox** model.
Everything runs on this Mac (Apple GPU / MPS). No account, no upload, no per-character cost.

## Start
```bash
./run.sh            # opens http://127.0.0.1:7860
```

1. **Create voice** – read the on-screen script into the mic (or upload old recordings),
   click *Add this sample* after each one, fill in name / labels, tick consent, **Save voice**, then **Preview**.
2. **Speak / Podcast** – paste any length of text, pick your voice, Generate. Download WAV/MP3.
   Multi-voice podcast: start lines with a saved voice name, e.g.
   ```
   Ramesh: Welcome to the show!
   Priya: Thanks for having me.
   ```

## Command line
```bash
./say --list
./say --voice Ramesh "Hello from my cloned voice"
./say --voice Ramesh --file episode1.txt --out episode1     # -> outputs/episode1.wav + .mp3
./say --create Ramesh --samples ~/Desktop/rec1.m4a ~/Desktop/rec2.m4a
./say --voice Ramesh --lang te "నమస్కారం, ఇది నా గొంతు"           # Telugu
```

## Indian languages (Telugu, Hindi, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Odia, Assamese)
These use **IndicF5** (AI4Bharat, MIT) in a separate venv. Other languages (Spanish, French, Japanese…) use Chatterbox.

One-time setup:
1. Accept the model terms at https://huggingface.co/ai4bharat/IndicF5 (logged in to Hugging Face), and
   make sure this machine is logged in: `.venv-indic/bin/huggingface-cli login`.
2. If `.venv-indic/` is missing:
   `uv venv --python 3.11 .venv-indic && uv pip install --python .venv-indic/bin/python -r requirements-indic.txt`

For a natural accent, in **Create voice → Step 4** record yourself reading the one sentence shown for each
language (under 14 s; the transcript must match exactly what you said). Without it, your main recording is
used and auto-transcribed — it works but sounds like English-accented Telugu/Hindi.
CLI: `./say --voice Ramesh --indic-sample te my_telugu.m4a`

Expressiveness / pace sliders apply to Chatterbox languages only.

### Translate → review → listen
In **Speak / Podcast**, pick an Indian language. Type or paste **English**, press **🌐 Translate to Telugu**
(or just Generate — it translates first). The translation appears in an editable box: **review and fix it**,
then press **Generate** and listen. Edit the text and Generate again until it sounds right.
`Speaker:` tags and paragraphs are kept. Text already in Telugu/Hindi script is not re-translated.

Translation runs locally: AI4Bharat **IndicTrans2** if you've accepted its terms at
https://huggingface.co/ai4bharat/indictrans2-en-indic-1B (best quality), otherwise Meta **NLLB-200**
(no sign-up; non-commercial license).

## Getting the best quality
- Quiet room, no echo, mic ~15 cm away. **Clean 30–60 s beats noisy 5 min.**
- Speak in the style you want back (podcast energy → read energetically).
- *Expressiveness* 0.5 = neutral, 0.7–0.9 = lively. If speech gets fast, lower *Pace* to ~0.3.
- Re-save the voice with a better recording any time — it overwrites the old one.

## Files
- `voices/<name>/` – your samples, cleaned `reference.wav`, metadata
- `outputs/` – generated audio
- `engine.py` core · `studio.py` studio UI · `server.py` hosted API · `app/` Next.js site (Vercel) · `say.py` CLI · `indic_worker.py` IndicF5 runner

Generated audio carries Chatterbox's built-in inaudible watermark (Perth). Only clone voices you own or have permission to use.

## Online: Vercel site + Hugging Face Space
Vercel can't run the voice models (GBs of weights, minutes per job), so:

```
Browser ──► Vercel (app/, Next.js, password login) ──API key──► HF Space (server.py: engine + studio UI)
   ▲                                                                   │
   └──────────── signed, expiring MP3 link (served by the Space) ◄─────┘
```
Voices are stored in a **private HF dataset** (`<user>/myvoice-voices`), synced by the Space.

### 1. Engine on Hugging Face
```bash
.venv/bin/python deploy/push_space.py --upload-voices
```
Creates the Space (Docker) + private voices dataset, sets secrets, uploads code. Generated
`MYVOICE_API_KEY` / `MYVOICE_UI_PASSWORD` are saved in `deploy/.secrets.env` (git-ignored).
Free CPU works but is slow; for speed pick a GPU (e.g. Nvidia T4 small) in Space → Settings → Hardware
and set a sleep time so you only pay while it's in use.
Studio (record/create voices): `https://<user>-myvoice.hf.space` — user `admin`, password from the secrets file.

### 2. Website on Vercel
The site lives at the repo root (`app/`, `lib/`, `middleware.ts`); `.vercelignore` keeps the Python
engine out of the Vercel build. In the Vercel project add these environment variables:

| Name | Value |
|---|---|
| `SPACE_URL` | `https://<user>-myvoice.hf.space` |
| `MYVOICE_API_KEY` | from `deploy/.secrets.env` |
| `SITE_PASSWORD` | the password you'll type to use the site |
| `SESSION_SECRET` | any long random string |

Redeploy. Local dev: `SPACE_URL=http://localhost:7860 ... npx next dev` with `uvicorn server:app`.
