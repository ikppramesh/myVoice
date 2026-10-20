"""Create/update the Hugging Face Space that hosts the myVoice engine.

Usage (from the repo root):
  .venv/bin/python deploy/push_space.py [--space ikppramesh/myvoice] [--upload-voices]

- Creates the Space (Docker, free CPU; upgrade hardware in the Space settings) and a private dataset
  <user>/myvoice-voices that stores your voices.
- Sets Space secrets: HF_TOKEN (this machine's token, for gated models + the dataset),
  MYVOICE_API_KEY and MYVOICE_UI_PASSWORD (generated once, kept in deploy/.secrets.env).
- Uploads the engine code. --upload-voices also copies your local voices/ into the private dataset.
"""
import argparse
import secrets
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi, get_token

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / "deploy" / ".secrets.env"
CODE = ["Dockerfile", "server.py", "studio.py", "engine.py", "indic_worker.py", "translate_worker.py",
        "requirements.txt", "requirements-indic.txt"]


def load_secrets():
    vals = {}
    if SECRETS.exists():
        for line in SECRETS.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                vals[k] = v
    vals.setdefault("MYVOICE_API_KEY", secrets.token_urlsafe(32))
    vals.setdefault("MYVOICE_UI_PASSWORD", secrets.token_urlsafe(12))
    SECRETS.write_text("".join(f"{k}={v}\n" for k, v in vals.items()))
    SECRETS.chmod(0o600)
    return vals


def main():
    api = HfApi()
    user = api.whoami()["name"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", default=f"{user}/myvoice")
    ap.add_argument("--voices-repo", default=f"{user}/myvoice-voices")
    ap.add_argument("--upload-voices", action="store_true")
    a = ap.parse_args()
    vals = load_secrets()

    api.create_repo(a.voices_repo, repo_type="dataset", private=True, exist_ok=True)
    if a.upload_voices:
        api.upload_folder(repo_id=a.voices_repo, repo_type="dataset", folder_path=ROOT / "voices",
                          ignore_patterns=["conds_*.pt", "*/conds_*.pt"], commit_message="Upload voices")

    api.create_repo(a.space, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    api.add_space_secret(a.space, "HF_TOKEN", get_token())
    api.add_space_secret(a.space, "MYVOICE_API_KEY", vals["MYVOICE_API_KEY"])
    api.add_space_secret(a.space, "MYVOICE_UI_PASSWORD", vals["MYVOICE_UI_PASSWORD"])
    api.add_space_variable(a.space, "MYVOICE_VOICES_REPO", a.voices_repo)

    with tempfile.TemporaryDirectory() as tmp:
        for f in CODE:
            shutil.copy(ROOT / f, Path(tmp) / f)
        shutil.copy(ROOT / "deploy" / "space_README.md", Path(tmp) / "README.md")
        api.upload_folder(repo_id=a.space, repo_type="space", folder_path=tmp, commit_message="Deploy myVoice")

    host = a.space.replace("/", "-").replace("_", "-").lower()
    print(f"Space:        https://huggingface.co/spaces/{a.space}")
    print(f"Engine URL:   https://{host}.hf.space   (studio login: admin / see {SECRETS.name})")
    print(f"Secrets file: {SECRETS}")


if __name__ == "__main__":
    main()
