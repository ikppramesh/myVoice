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
./say --voice Ramesh --lang hi "नमस्ते, यह मेरी आवाज़ है"      # 23 languages incl. Hindi
```

## Getting the best quality
- Quiet room, no echo, mic ~15 cm away. **Clean 30–60 s beats noisy 5 min.**
- Speak in the style you want back (podcast energy → read energetically).
- *Expressiveness* 0.5 = neutral, 0.7–0.9 = lively. If speech gets fast, lower *Pace* to ~0.3.
- Re-save the voice with a better recording any time — it overwrites the old one.

## Files
- `voices/<name>/` – your samples, cleaned `reference.wav`, metadata
- `outputs/` – generated audio
- `engine.py` core · `app.py` web UI · `say.py` CLI

Generated audio carries Chatterbox's built-in inaudible watermark (Perth). Only clone voices you own or have permission to use.
