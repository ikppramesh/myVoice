#!/usr/bin/env python
"""Command-line voice generation.

Examples:
  ./say --voice Ramesh "Hello world"
  ./say --voice Ramesh --file episode1.txt --out episode1
  ./say --create Ramesh --samples rec1.m4a rec2.wav
  ./say --list
"""
import argparse
import sys
from pathlib import Path

import engine


def main():
    ap = argparse.ArgumentParser(description="Speak text in your cloned voice (runs locally).")
    ap.add_argument("text", nargs="?", help="text to speak (or use --file / stdin)")
    ap.add_argument("--voice", "-v", help="saved voice name")
    ap.add_argument("--file", "-f", help="read text/script from a file")
    ap.add_argument("--out", "-o", help="output file name (without extension), saved in outputs/")
    ap.add_argument("--lang", help="language code, e.g. en, hi, es (default: the voice's language)")
    ap.add_argument("--exaggeration", type=float, default=0.5)
    ap.add_argument("--cfg", type=float, default=0.5)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--create", metavar="NAME", help="create a voice from --samples")
    ap.add_argument("--samples", nargs="+", help="audio files for --create")
    ap.add_argument("--list", action="store_true", help="list saved voices")
    a = ap.parse_args()

    if a.list:
        for v in engine.list_voices():
            print(f"{v['id']:20} {v['language']:4} {v['reference_seconds']:>5}s  {v['description']}")
        return
    if a.create:
        vdir = engine.save_voice(a.create, a.samples or [], language=a.lang or "en")
        print(f"Saved voice to {vdir}")
        return

    text = Path(a.file).read_text() if a.file else (a.text or sys.stdin.read())
    if not a.voice:
        ap.error("--voice is required")
    wav, mp3 = engine.speak(text, a.voice, language=a.lang, exaggeration=a.exaggeration,
                            cfg_weight=a.cfg, temperature=a.temperature, seed=a.seed, out_name=a.out,
                            progress=lambda f, msg: print(f"  {msg}", file=sys.stderr))
    print(wav)
    print(mp3)


if __name__ == "__main__":
    main()
