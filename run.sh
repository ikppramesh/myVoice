#!/bin/zsh
# Start the myVoice studio at http://127.0.0.1:7860
cd "$(dirname "$0")"
export PYTORCH_ENABLE_MPS_FALLBACK=1
exec .venv/bin/python app.py
