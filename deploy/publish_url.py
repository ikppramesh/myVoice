"""Publish the engine's current public URL to the site's Edge Config (read by lib/space.ts per request).

Usage: .venv/bin/python deploy/publish_url.py https://xyz.trycloudflare.com
       .venv/bin/python deploy/publish_url.py --refresh-login     # just keep the Vercel CLI login fresh
Auth: VERCEL_ENGINE_TOKEN in deploy/.secrets.env if set, else the Vercel CLI login, which is refreshed by
running the CLI first (its access token expires; the CLI renews it with the stored refresh token).
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / "deploy" / ".secrets.env"
CLI_AUTH = Path.home() / "Library/Application Support/com.vercel.cli/auth.json"


def secrets():
    return dict(l.split("=", 1) for l in SECRETS.read_text().splitlines() if "=" in l)


def refresh_cli_login():
    subprocess.run(["npx", "--yes", "vercel@latest", "whoami"], cwd=ROOT, capture_output=True, timeout=180)


def token(vals):
    if vals.get("VERCEL_ENGINE_TOKEN"):
        return vals["VERCEL_ENGINE_TOKEN"]
    refresh_cli_login()
    return json.loads(CLI_AUTH.read_text())["token"]


def publish(url):
    vals = secrets()
    store, team = vals["EDGE_CONFIG_ID"], vals["VERCEL_TEAM_ID"]
    body = json.dumps({"items": [{"operation": "upsert", "key": "engineUrl", "value": url}]}).encode()
    for attempt in range(5):
        req = urllib.request.Request(f"https://api.vercel.com/v1/edge-config/{store}/items?teamId={team}",
                                     data=body, method="PATCH",
                                     headers={"Authorization": f"Bearer {token(vals)}",
                                              "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=30)
            print(f"Published engine URL {url}")
            return True
        except (urllib.error.URLError, TimeoutError) as e:
            detail = e.read()[:200] if isinstance(e, urllib.error.HTTPError) else e
            print(f"Publish attempt {attempt + 1} failed: {detail}", file=sys.stderr)
            time.sleep(10 * (attempt + 1))
    return False


if __name__ == "__main__":
    if sys.argv[1:] == ["--refresh-login"]:
        refresh_cli_login()
    else:
        sys.exit(0 if publish(sys.argv[1].rstrip("/")) else 1)
