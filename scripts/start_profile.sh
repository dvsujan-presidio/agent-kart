#!/usr/bin/env bash
# Serves ONLY the public AgentKart agent profile and exposes it via a Cloudflare quick tunnel.
# Real stores fetch this URL on every request. Writes the URL to .run/profile_url (the API reads it).
# For a stable URL, host agent_profile/agent-profile.json on any static HTTPS host and set AGENT_PROFILE_URL.
set -e
cd "$(dirname "$0")/.."
mkdir -p .run
pkill -f "agent_profile.serve" 2>/dev/null || true
pkill -f "cloudflared tunnel" 2>/dev/null || true
sleep 1
PYTHONPATH=. nohup uv run uvicorn agent_profile.serve:app --port 8300 > .run/profile.log 2>&1 < /dev/null &
nohup cloudflared tunnel --url http://localhost:8300 --no-autoupdate > .run/tunnel.log 2>&1 < /dev/null &
for i in $(seq 1 30); do
  URL=$(grep -o "https://[a-z0-9-]*\.trycloudflare\.com" .run/tunnel.log | head -1 || true)
  [ -n "$URL" ] && break; sleep 1
done
[ -z "$URL" ] && { echo "tunnel did not start (see .run/tunnel.log)"; exit 1; }
FULL="$URL/.well-known/agentkart-agent-profile.json"
for i in $(seq 1 20); do curl -sf -o /dev/null "$FULL" && break; sleep 1; done
echo "$FULL" > .run/profile_url
echo "agent profile: $FULL"
