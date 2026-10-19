# Hugging Face Space (Docker SDK) image for the myVoice engine. Uses the GPU when the Space has one.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

# Two venvs, same as local: Chatterbox (+ server) and IndicF5/translation, whose pins conflict.
COPY --chown=user requirements.txt requirements-indic.txt ./
RUN pip install --no-cache-dir --user uv \
    && uv venv --python python3.11 .venv \
    && uv pip install --no-cache --python .venv/bin/python -r requirements.txt fastapi uvicorn \
    && uv venv --python python3.11 .venv-indic \
    && uv pip install --no-cache --python .venv-indic/bin/python -r requirements-indic.txt

COPY --chown=user . .

ENV MYVOICE_DATA=/home/user/data \
    HF_HOME=/home/user/.cache/huggingface \
    PYTHONUNBUFFERED=1
EXPOSE 7860
CMD [".venv/bin/uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
