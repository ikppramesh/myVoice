#!/bin/zsh
# Run the voice engine on this Mac and expose its API to the Vercel site through a Cloudflare tunnel.
#   Studio (record/manage voices): http://127.0.0.1:7860   (this Mac only)
# The quick-tunnel URL changes whenever the tunnel restarts; each new URL is published to the site's
# Edge Config (deploy/publish_url.py) and the site picks it up within seconds, without a redeploy.
# A watchdog restarts the tunnel when its public URL stops answering, and exits (so launchd restarts
# everything) if the engine dies. Keeps the Mac awake while running.
# Run it as a login service that restarts itself: deploy/install_agent.sh
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/opt/homebrew/opt/node/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export PYTORCH_ENABLE_MPS_FALLBACK=1 MYVOICE_UI_LOCAL_ONLY=1
if [[ ! -f deploy/.secrets.env ]] || ! grep -q '^MYVOICE_API_KEY=' deploy/.secrets.env; then
  mkdir -p deploy
  echo "MYVOICE_API_KEY=$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')" >> deploy/.secrets.env
  chmod 600 deploy/.secrets.env
fi
export MYVOICE_API_KEY="$(grep '^MYVOICE_API_KEY=' deploy/.secrets.env | cut -d= -f2-)"
CF=$(command -v cloudflared || echo .bin/cloudflared)
TUNNEL_LOG=~/Library/Logs/myvoice-tunnel.log
log() { echo "$(date '+%F %T') $*"; }

# Idle sleep drops the tunnel; hold the Mac awake for as long as this script lives.
caffeinate -is -w $$ &

lsof -ti :7860 | xargs kill 2>/dev/null
pkill -f "cloudflared tunnel --no-autoupdate --url http://127.0.0.1:7860" 2>/dev/null
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 7860 &
SERVER=$!
TUNNEL=""
trap 'kill $SERVER $TUNNEL 2>/dev/null' EXIT
until curl -sf http://127.0.0.1:7860/api/v1/health >/dev/null; do
  kill -0 $SERVER 2>/dev/null || { log "Engine failed to start"; exit 1; }
  sleep 1
done
log "Engine ready. Studio: http://127.0.0.1:7860"

last_refresh=$(date +%s)
while true; do
  # Start a tunnel and wait for its URL.
  : > "$TUNNEL_LOG"
  "$CF" tunnel --no-autoupdate --url http://127.0.0.1:7860 >> "$TUNNEL_LOG" 2>&1 &
  TUNNEL=$!
  URL=""
  for i in {1..60}; do
    URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$TUNNEL_LOG" | head -1)
    [[ -n "$URL" ]] && break
    kill -0 $TUNNEL 2>/dev/null || break
    sleep 1
  done
  if [[ -z "$URL" ]]; then
    log "Tunnel did not start; retrying in 15s"; kill $TUNNEL 2>/dev/null; sleep 15; continue
  fi
  log "Tunnel: $URL"
  for i in {1..30}; do curl -sf --max-time 10 "$URL/api/v1/health" >/dev/null && break; sleep 2; done
  published=0
  .venv/bin/python deploy/publish_url.py "$URL" && published=1

  # Watchdog.
  fails=0
  while true; do
    sleep 30
    if ! curl -sf --max-time 10 http://127.0.0.1:7860/api/v1/health >/dev/null; then
      log "Engine stopped answering; exiting so launchd restarts it"; exit 1
    fi
    if ! kill -0 $TUNNEL 2>/dev/null; then log "Tunnel process exited; restarting tunnel"; break; fi
    if curl -sf --max-time 15 "$URL/api/v1/health" >/dev/null; then fails=0; else ((fails++)); fi
    if (( fails >= 4 )); then log "Tunnel URL unreachable for 2 min; restarting tunnel"; kill $TUNNEL; break; fi
    if (( ! published )); then .venv/bin/python deploy/publish_url.py "$URL" && published=1; fi
    if (( $(date +%s) - last_refresh > 86400 )); then
      .venv/bin/python deploy/publish_url.py --refresh-login; last_refresh=$(date +%s)
    fi
  done
  wait $TUNNEL 2>/dev/null
done
