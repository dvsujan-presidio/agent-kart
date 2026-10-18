# Setup and run

## Prerequisites
- Python 3.12 and [`uv`](https://docs.astral.sh/uv/), Node 20+ and `pnpm`
- A Microsoft Foundry resource with a model deployment, an Azure AI Speech resource, and a LiveKit Cloud project (see [azure-setup.md](azure-setup.md))
- For **real stores**: a US network exit (some stores are region-limited) and `cloudflared` (for the agent-profile tunnel)

## Install
```bash
uv sync --group dev --group voice
(cd web && pnpm install)
cp .env.example .env      # then fill in the values below
```

## Configuration (`.env`)
| Variable | Needed | Purpose |
|---|---|---|
| `FOUNDRY_RESOURCE`, `MODEL_ENDPOINT`, `MODEL_API_VERSION` | yes | Your Foundry resource name and endpoint |
| `MODEL_API_KEY` | yes | Key from the Foundry resource (Keys and Endpoint) |
| `MODEL_DEPLOYMENT`, `MODEL_DEPLOYMENT_FAST` | yes | Deployment names (no model name is hardcoded) |
| `APPROVAL_HMAC_SECRET` | yes | Long random value that signs approval tokens |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | for voice | From your LiveKit Cloud project |
| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | for voice | Azure AI Speech |
| `STT_LANGUAGES`, `TTS_VOICE` | optional | Default `en-IN` and `en-IN-NeerjaNeural` |
| `REAL_STORE_MODE`, `REAL_STORE_SEARCH`, `REAL_STORE_CART`, `REAL_STORE_HANDOFF` | optional | Feature flags for real stores (all on by default) |
| `REAL_STORE_REPLAY`, `REAL_STORE_RECORD` | optional | Replay or record store responses |
| `AGENT_PROFILE_URL` | optional | Stable public URL of the agent profile. If empty, the tunnel URL written by `make profile` is used. |
| `DEMO_MODE` | optional | Enables the "simulate delay" and reset endpoints |

Never commit `.env`.

## Run everything
```bash
make start      # 4 mock stores, agent-profile tunnel, API :8000, web :3000, voice worker
open http://localhost:3000
make stop
```
Set `NO_VOICE=1` or `NO_REAL=1` to skip the voice worker or the real-store tunnel.

## Try it
1. **Demo stores:** tap *Talk to AgentKart* (or type): "Help me shop for a birthday party for 10 people tomorrow evening, under three thousand rupees. I already have plates." Answer the questions, say "place the order", then "yes, place the order". Use *Simulate cake delay* to see the backup flow.
2. **Real stores:** "Plan a camping weekend for 4 people, budget 4000 dollars", then "add to carts". Use **Open cart** on a store.
3. **Addresses:** answer "no, deliver somewhere else" to the saved-address question and the agent collects street, pincode and city.

## Commands
| Command | What it does |
|---|---|
| `make test` | all tests (150) |
| `make eval` | deterministic evals, writes `evals/report/index.html` |
| `make demo` | the whole demo story through the API with the real model |
| `make ui-test`, `make ui-real-test` | drive the real web UI in headless Chromium (the second uses live real stores) |
| `make voice-test` | speak the demo into LiveKit and check the replies |
| `make probe-real` | what each real store returns per category (live) |
| `make profile` | (re)start the agent-profile tunnel |
| `make check-model` | one call to the model deployment |
| `make types` | regenerate TypeScript types from the contracts |

## Troubleshooting
| Symptom | Likely cause and fix |
|---|---|
| "Real stores need a public agent profile" | The tunnel is down. Run `make profile` and check `.run/tunnel.log`. |
| "Real stores are unreachable right now" | The profile URL is not reachable by stores, or you are on a blocked region. Check `curl localhost:8000/real/config`. |
| A real store is skipped | That store did not respond (rate limit or region). The rest still work. |
| New tunnel URL does not resolve on your machine | DNS lag on a brand-new hostname; stores can still reach it. Wait a minute. |
| `make check-model` says deployment not found | `MODEL_DEPLOYMENT` must equal the deployment name in Foundry exactly. |
| Voice button errors | `LIVEKIT_*` missing, or the worker is not running (`make voice`). |
| First real-store answer takes 10-20 s | Planning and live searches; results are cached for 10 minutes. |
