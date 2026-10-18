# AgentKart

**A voice-first agent that gets a job done, not just a product.**
*Copilot Checkout helps you buy a product. AgentKart helps you get a job done.*

Say "birthday party for 10 tomorrow evening, under ₹3,000, I already have plates" (or "camping weekend for 4").
AgentKart asks a few natural questions, plans the whole list, works out the right quantities, finds the cheapest valid
basket across stores including delivery fees, respects your deadline and budget, reads the order back, and acts only after
your explicit yes.

![AgentKart](docs/images/02-basket-demo-stores.png)

## What it does
- **Voice-first** over LiveKit, with Azure AI Speech for speech and a Microsoft Foundry model for understanding and planning. Typing works too.
- **Quantities and money are exact.** The model only parses and phrases; quantities, fees, totals, trade-offs and splits come from tested Python.
- **Deadline and budget aware.** Late offers are excluded and explained; over budget gives ranked trade-offs; costs split exactly.
- **You approve every order.** A signed token bound to the exact basket is required, from a click or a spoken yes judged by deterministic code.
- **Watches after purchase.** A delay triggers a spoken backup proposal that needs its own approval.
- **Open standard.** Every store is discovered through UCP (`/.well-known/ucp`).
- **Real stores, dynamically planned.** For any request the agent plans the list, searches live US stores over UCP/MCP, and **adds to carts only**. It never orders or pays on real stores.

## Documentation
Start at **[docs/README.md](docs/README.md)**.

| | |
|---|---|
| [Solution overview](docs/solution-overview.md) | problem, solution, user journeys, screenshots |
| [Architecture and diagrams](docs/architecture.md) | system context, components, sequence and state diagrams, data model |
| [Microsoft services](docs/microsoft-services.md) | what is used, and what is not |
| [Security and responsible AI](docs/security-and-responsible-ai.md) | guarantees, threat model, privacy, known gaps |
| [API reference](docs/api.md) | endpoints and events |
| [Setup and run](docs/setup-and-run.md), [Azure setup](docs/azure-setup.md) | install, configuration, troubleshooting |
| [Demo script](docs/demo-script.md) | the rehearsed demo and its numbers |
| [Testing and evals](docs/testing-and-evals.md) | 150 tests, 108 eval scenarios at 100% |
| [Limitations and roadmap](docs/limitations-and-roadmap.md) | honest scope |

![Architecture](docs/diagrams/01-system-context.png)

## Quick start
Prerequisites: Python 3.12 with `uv`, Node 20 with `pnpm`, and a Foundry model, Azure Speech and a LiveKit project (see [setup](docs/setup-and-run.md)).

```bash
uv sync --group dev --group voice && (cd web && pnpm install)
cp .env.example .env        # fill in your own values; never commit .env
make start                  # mock stores, API :8000, web :3000, voice worker, agent-profile tunnel
open http://localhost:3000
make stop
```

Then tap **Talk to AgentKart** (or type) and try the sentence above. `make test` runs the 150 tests, `make eval` the deterministic evals.

## Repository layout
`domain/` pure logic · `agent/app/` API, orchestrator, NLU, planner, approval gate · `agent/app/real_stores/` UCP-over-MCP ·
`stores/` mock merchants · `voice/` LiveKit worker and confirmation gate · `web/` Next.js · `contracts/` shared models ·
`infra/` Bicep (not deployed) · `evals/`, `scripts/` checks and demos · `docs/` documentation.

## Honest scope
The app runs locally. Azure Container Apps, Cosmos DB and a Teams / M365 Copilot agent are designed but not built, and the API has no
user authentication yet. The mock stores implement a simplified UCP subset. See [limitations](docs/limitations-and-roadmap.md).
