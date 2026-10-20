#!/bin/zsh
# Run the voice engine on this Mac and expose its API to the Vercel site through a Cloudflare tunnel.
#   Studio (record/manage voices): http://127.0.0.1:7860   (this Mac only)
#   Vercel env: SPACE_URL = the https://….trycloudflare.com URL printed below, MYVOICE_API_KEY = from deploy/.secrets.env
# Quick-tunnel URLs change every time this starts; update SPACE_URL in Vercel and redeploy when it does.
cd "$(dirname "$0")"
export PYTORCH_ENABLE_MPS_FALLBACK=1 MYVOICE_UI_LOCAL_ONLY=1
if [[ ! -f deploy/.secrets.env ]] || ! grep -q '^MYVOICE_API_KEY=' deploy/.secrets.env; then
  mkdir -p deploy
  echo "MYVOICE_API_KEY=$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')" >> deploy/.secrets.env
  chmod 600 deploy/.secrets.env
fi
export MYVOICE_API_KEY="$(grep '^MYVOICE_API_KEY=' deploy/.secrets.env | cut -d= -f2-)"

lsof -ti :7860 | xargs kill 2>/dev/null
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 7860 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
until curl -sf http://127.0.0.1:7860/api/v1/health >/dev/null; do sleep 1; done
echo "Engine ready. Studio: http://127.0.0.1:7860"
CF=$(command -v cloudflared || echo .bin/cloudflared)
"$CF" tunnel --no-autoupdate --url http://127.0.0.1:7860 2>&1 | while read -r line; do
  if [[ "$line" =~ (https://[a-z0-9-]+\.trycloudflare\.com) ]]; then
    echo "\n==> SPACE_URL for Vercel: ${match[1]}\n"
  fi
done
