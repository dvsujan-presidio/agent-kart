#!/usr/bin/env bash
# Starts the whole local stack in the background: 4 mock stores, API, web, voice worker.
set -e
cd "$(dirname "$0")/.."
mkdir -p .run
"$(dirname "$0")/stop_all.sh" >/dev/null 2>&1 || true
export PYTHONPATH=.:agent
nohup uv run python -m stores.run_all > .run/stores.log 2>&1 < /dev/null &
sleep 3
if [ "${NO_REAL:-0}" != "1" ]; then
  ./scripts/start_profile.sh || echo "real stores disabled: agent profile tunnel did not start"
fi
nohup uv run uvicorn app.main:app --app-dir agent --port 8000 > .run/api.log 2>&1 < /dev/null &
(cd web && nohup pnpm dev --port 3000 > ../.run/web.log 2>&1 &)
if [ "${NO_VOICE:-0}" != "1" ]; then
  PYTHONPATH=. nohup uv run python -m voice.worker dev > .run/voice.log 2>&1 < /dev/null &
fi
echo "waiting for services..."
for i in $(seq 1 40); do
  curl -sf localhost:8000/health >/dev/null && curl -sf -o /dev/null localhost:3000 && break; sleep 1
done
curl -s localhost:8000/health; echo
echo "Web:   http://localhost:3000"
echo "API:   http://localhost:8000/docs"
echo "Logs:  .run/*.log   Stop: scripts/stop_all.sh"
