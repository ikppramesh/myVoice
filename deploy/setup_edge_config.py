"""One-time setup: let the Vercel site find the engine's current tunnel URL at request time.

Quick-tunnel URLs change whenever the tunnel restarts. Instead of baking the URL into the site
(SPACE_URL env + redeploy, which is slow and failed silently), the engine writes its URL to a Vercel
Edge Config store and the site reads it on every request.

This script (run from the repo root, with the Vercel CLI logged in):
  1. creates the Edge Config store "myvoice-engine" (if missing),
  2. sets the project's EDGE_CONFIG env var (read-only connection string) for production + preview,
  3. saves the store id in deploy/.secrets.env for deploy/publish_url.py.

The engine updates the URL with the Vercel CLI login (refreshed automatically by running the CLI), or
with VERCEL_ENGINE_TOKEN from deploy/.secrets.env if you add one (vercel.com/account/tokens, no expiry).

Usage: .venv/bin/python deploy/setup_edge_config.py
"""
import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / "deploy" / ".secrets.env"
CLI_AUTH = Path.home() / "Library/Application Support/com.vercel.cli/auth.json"
SLUG = "myvoice-engine"


def api(method, path, token, team, body=None):
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(f"https://api.vercel.com{path}{sep}teamId={team}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} failed: HTTP {e.code} {e.read()[:400].decode(errors='replace')}")


def read_secrets():
    vals = {}
    if SECRETS.exists():
        for line in SECRETS.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                vals[k] = v
    return vals


def main():
    token = json.loads(CLI_AUTH.read_text())["token"]
    project = json.loads((ROOT / ".vercel" / "project.json").read_text())
    team, project_id = project["orgId"], project["projectId"]
    vals = read_secrets()

    store = next((e for e in api("GET", "/v1/edge-config", token, team) if e["slug"] == SLUG), None)
    if not store:
        store = api("POST", "/v1/edge-config", token, team, {"slug": SLUG, "items": {"engineUrl": ""}})
        print(f"Created Edge Config {SLUG} ({store['id']})")
    store_id = store["id"]

    read = api("POST", f"/v1/edge-config/{store_id}/token", token, team, {"label": "myvoice-site"})
    connection = f"https://edge-config.vercel.com/{store_id}?token={read['token']}"
    api("POST", f"/v10/projects/{project_id}/env?upsert=true", token, team,
        {"key": "EDGE_CONFIG", "value": connection, "type": "encrypted", "target": ["production", "preview"]})
    print("Set EDGE_CONFIG on the Vercel project (production + preview)")

    vals["VERCEL_TEAM_ID"] = team
    vals["EDGE_CONFIG_ID"] = store_id
    SECRETS.write_text("".join(f"{k}={v}\n" for k, v in vals.items()))
    SECRETS.chmod(0o600)
    print(f"Saved store id in {SECRETS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
