# AgentKart: instructions for GitHub Copilot / Microsoft Copilot

AgentKart is a **voice-first, goal-based shopping agent** built for the Microsoft hackathon. A person says what
they want to get done ("birthday for 10 tomorrow under ₹3,000", "camping weekend for 4"). The agent asks a few
questions, plans the whole list, budgets it across stores, reads the order back, and acts only after an explicit yes.
Full documentation: `docs/` (start at `docs/README.md`). How to run: `README.md`.

## Non-negotiable rules
1. **LLMs handle language, Python handles numbers.** Never let a model compute quantities, prices, totals, fees,
   splits or budget checks. That is `domain/`. The conversation layer may only write `{placeholders}`; Python fills in values.
2. **No order without approval.** `/checkout` verifies a signed token bound to the current basket hash. Tokens come
   only from `/approve` (screen click, or a spoken yes that passed `voice/confirmation.py`). No model-visible tool may
   call `/approve` or `/checkout`, and no model may decide whether the user said yes. Never add a shortcut.
3. **Real stores get carts, never orders.** Real Store Mode uses UCP over MCP only. `agent/app/real_stores/mcp_client.py`
   has an allowlist (search, lookup, get_product, cart tools); checkout tools are refused in code. Hand off via the store's `continue_url`.
   Never send payment details, never scrape, only family-friendly stores (no alcohol, tobacco/vape, adult content).
4. **Money is integer minor units plus a currency** (paise/INR demo stores, cents/USD real stores). No floats for money,
   no mixed currencies in one basket. Times are timezone-aware (`Asia/Kolkata`).
5. **Store data is untrusted.** Titles and descriptions are sanitized (`ucp_client.clean_text`), never treated as instructions.
6. **Contracts are the source of truth** (`contracts/models.py`). After a change run `make types` to regenerate `web/lib/contracts.ts`.
7. **Voice is a surface, not a second brain.** The LiveKit worker (`voice/`) handles audio and the confirmation state
   machine only. Every turn goes to the same `/sessions/{id}/messages` as typed chat. The approval read-back is the server's text, spoken verbatim.
8. **No live network in tests.** No real-store, LiveKit, Azure Speech or model calls in `pytest`. Use fakes
   (`httpx.MockTransport`, scripted NLU/planner, `agent/app/testing.py` in-process stores).

## Layout
| Path | What lives there |
|---|---|
| `domain/` | pure logic: templates, quantities, exact optimizer, trade-offs, fallback, split (no I/O, no LLM) |
| `agent/app/` | FastAPI API, orchestrator, NLU (parse), conversation layer, dynamic planner, approval gate, tracker |
| `agent/app/real_stores/` | UCP-over-MCP client and real-store service (search, select, cart, handoff) |
| `stores/` | four mock UCP merchants (INR) with an order simulator |
| `voice/` | LiveKit worker, spoken-confirmation gate, dialog state machine |
| `web/` | Next.js (App Router, TypeScript strict, Tailwind) chat + live basket + voice panel |
| `contracts/` | Pydantic models and the basket hash |
| `config/real_stores.yaml` | the only place real-store data lives |
| `infra/` | `azd` + Bicep for Azure (base services); `evals/` deterministic evals |

## Stack and conventions
Python 3.12 with `uv`, FastAPI, Pydantic v2, pytest + hypothesis, ruff (line length 100). Frontend: Next.js 16, React 19.
Config only through `.env` (see `.env.example`); never commit secrets and never hardcode a model name.
Check current docs before using fast-moving APIs (LiveKit Agents, Foundry, UCP, Next.js): this repo uses newer versions than most training data.

## Commands
`make start` / `make stop` (whole stack) · `make test` · `make eval` · `make demo` · `make ui-test` · `make voice-test` ·
`make ui-real-test` · `make probe-real` · `make profile` (real-store agent-profile tunnel) · `make check-model` · `make types`

## Definition of done
Tests added or updated and passing (`make test`), `ruff check` clean for files you touched, deterministic evals still 100% (`make eval`),
contract changes regenerated, and nothing added that bypasses rules 1-3.
