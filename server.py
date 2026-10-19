"""Hosted server: the Gradio studio (password-protected) plus a small job API for the Vercel site.

Run:  .venv/bin/uvicorn server:app --host 0.0.0.0 --port 7860

Environment:
  MYVOICE_API_KEY       required; the Vercel site sends it as the X-API-Key header
  MYVOICE_UI_PASSWORD   password for the studio UI (username "admin"); UI is open if unset (local use)
  MYVOICE_VOICES_REPO   optional private HF dataset that stores voices (see engine.py)

API (all JSON, X-API-Key required except /audio which uses a signed link):
  GET  /api/v1/voices                     -> [{id, name, language, labels, indic_samples}]
  POST /api/v1/jobs {type:"translate", text, lang}
  POST /api/v1/jobs {type:"speak", text, voice, lang, exaggeration?, cfg_weight?, temperature?, seed?}
  GET  /api/v1/jobs/{id}                  -> {status, progress, message, result}
  GET  /api/v1/audio/{file}?exp=..&sig=.. -> mp3 (link returned in a finished speak job)
"""
import hashlib
import hmac
import os
import queue
import threading
import time
import uuid

import gradio as gr
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import engine

API_KEY = os.environ.get("MYVOICE_API_KEY", "")
UI_PASSWORD = os.environ.get("MYVOICE_UI_PASSWORD")
LINK_TTL = 6 * 3600
MAX_TEXT_CHARS = 20000

engine.pull_voices()
import app as studio  # noqa: E402  (after pull so the UI lists synced voices)

jobs: dict[str, dict] = {}
work: "queue.Queue[str]" = queue.Queue()


def require_key(x_api_key: str = Header(default="")):
    if not API_KEY or not hmac.compare_digest(x_api_key, API_KEY):
        raise HTTPException(401, "Invalid API key")


def sign(name: str, exp: int) -> str:
    return hmac.new(API_KEY.encode(), f"{name}:{exp}".encode(), hashlib.sha256).hexdigest()


class Job(BaseModel):
    type: str
    text: str
    lang: str = "en"
    voice: str | None = None
    exaggeration: float = 0.5
    cfg_weight: float = 0.5
    temperature: float = 0.8
    seed: int | None = 42


def run_job(job_id: str):
    job = jobs[job_id]
    req: Job = job["req"]
    job.update(status="running", started=time.time())

    def progress(frac, msg=""):
        job.update(progress=round(float(frac), 3), message=msg)

    try:
        if req.type == "translate":
            progress(0.1, "Translating…")
            text, model = engine.translate(req.text, req.lang)
            job["result"] = {"text": text, "model": model}
        else:
            wav, mp3 = engine.speak(req.text, req.voice, language=req.lang, exaggeration=req.exaggeration,
                                    cfg_weight=req.cfg_weight, temperature=req.temperature, seed=req.seed,
                                    out_name=f"web_{job_id}", progress=progress)
            wav.unlink(missing_ok=True)
            exp = int(time.time()) + LINK_TTL
            job["result"] = {"audio": f"/api/v1/audio/{mp3.name}?exp={exp}&sig={sign(mp3.name, exp)}"}
        job.update(status="done", progress=1.0, message="Done")
    except Exception as e:  # report to the caller instead of killing the worker
        job.update(status="error", message=str(e))


def worker():
    while True:
        job_id = work.get()
        try:
            run_job(job_id)
        finally:
            work.task_done()


threading.Thread(target=worker, daemon=True).start()

app = FastAPI(title="myVoice")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=[])


@app.get("/api/v1/health")
def health():
    return {"ok": True, "device": engine.DEVICE, "queued": work.qsize()}


@app.get("/api/v1/voices", dependencies=[Depends(require_key)])
def voices():
    return [{"id": v["id"], "name": v["name"], "language": v["language"], "labels": v["labels"],
             "indic_samples": engine.indic_references(v["id"])} for v in engine.list_voices()]


@app.get("/api/v1/languages", dependencies=[Depends(require_key)])
def languages():
    return [{"code": code, "name": name, "indian": code in engine.INDIC_LANGS} for code, name in studio.LANGS.items()]


@app.post("/api/v1/jobs", dependencies=[Depends(require_key)])
def create_job(req: Job):
    if req.type not in ("translate", "speak"):
        raise HTTPException(400, "type must be 'translate' or 'speak'")
    if not req.text.strip() or len(req.text) > MAX_TEXT_CHARS:
        raise HTTPException(400, f"text must be 1–{MAX_TEXT_CHARS} characters")
    if req.type == "speak":
        try:
            engine.voice_dir(req.voice or "")
        except ValueError as e:
            raise HTTPException(404, str(e))
    if req.type == "translate" and req.lang not in engine.FLORES:
        raise HTTPException(400, "translation is only for Indian languages")
    # drop finished jobs older than a day
    for jid in [j for j, v in jobs.items() if time.time() - v["created"] > 86400]:
        jobs.pop(jid, None)
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"req": req, "status": "queued", "progress": 0.0, "message": "Waiting in queue…",
                    "result": None, "created": time.time()}
    work.put(job_id)
    return {"id": job_id}


@app.get("/api/v1/jobs/{job_id}", dependencies=[Depends(require_key)])
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job")
    return {k: job[k] for k in ("status", "progress", "message", "result")}


@app.get("/api/v1/audio/{name}")
def audio(name: str, exp: int, sig: str):
    if exp < time.time() or not hmac.compare_digest(sig, sign(name, exp)):
        raise HTTPException(403, "Link expired or invalid")
    path = engine.OUTPUT_DIR / name
    if path.parent != engine.OUTPUT_DIR or path.suffix != ".mp3" or not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type="audio/mpeg", filename=name)


app = gr.mount_gradio_app(app, studio.demo.queue(), path="/",
                          auth=("admin", UI_PASSWORD) if UI_PASSWORD else None)
