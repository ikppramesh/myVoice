#!/bin/zsh
# Run the voice engine on this Mac and expose its API to the Vercel site through a Cloudflare tunnel.
#   Studio (record/manage voices): http://127.0.0.1:7860   (this Mac only)
#   Vercel env: SPACE_URL = the tunnel URL, MYVOICE_API_KEY = from deploy/.secrets.env
# Quick-tunnel URLs change every time this starts, so a new URL is pushed to Vercel's SPACE_URL and the
# production site is redeployed automatically. Keeps the Mac awake while running.
# To keep it running across logins/crashes: deploy/install_agent.sh
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/opt/homebrew/opt/node/bin:/usr/local/bin:$PATH"
export PYTORCH_ENABLE_MPS_FALLBACK=1 MYVOICE_UI_LOCAL_ONLY=1
VERCEL_SITE=myvoice-ir.vercel.app
if [[ ! -f deploy/.secrets.env ]] || ! grep -q '^MYVOICE_API_KEY=' deploy/.secrets.env; then
  mkdir -p deploy
  echo "MYVOICE_API_KEY=$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')" >> deploy/.secrets.env
  chmod 600 deploy/.secrets.env
fi
export MYVOICE_API_KEY="$(grep '^MYVOICE_API_KEY=' deploy/.secrets.env | cut -d= -f2-)"

# Idle sleep drops the tunnel; hold the Mac awake for as long as this script lives.
caffeinate -is -w $$ &

lsof -ti :7860 | xargs kill 2>/dev/null
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 7860 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
until curl -sf http://127.0.0.1:7860/api/v1/health >/dev/null; do
  kill -0 $SERVER 2>/dev/null || { echo "Engine failed to start"; exit 1; }
  sleep 1
done
echo "Engine ready. Studio: http://127.0.0.1:7860"

publish_url() {
  local url=$1
  # Wait until the new tunnel actually answers before pointing the site at it.
  for i in {1..30}; do curl -sf "$url/api/v1/health" >/dev/null && break; sleep 2; done
  if [[ "$url" == "$(cat deploy/.tunnel_url 2>/dev/null)" ]]; then return; fi
  echo "==> Updating Vercel SPACE_URL to $url and redeploying $VERCEL_SITE"
  npx --yes vercel env update SPACE_URL -e production --value "$url" --yes \
    && npx --yes vercel redeploy "$VERCEL_SITE" --environment production \
    && echo "$url" > deploy/.tunnel_url \
    && echo "==> Site now uses $url"
}

CF=$(command -v cloudflared || echo .bin/cloudflared)
"$CF" tunnel --no-autoupdate --url http://127.0.0.1:7860 2>&1 | while read -r line; do
  if [[ "$line" =~ (https://[a-z0-9-]+\.trycloudflare\.com) ]]; then
    echo "\n==> Tunnel: ${match[1]}\n"
    publish_url "${match[1]}" &
  fi
done
