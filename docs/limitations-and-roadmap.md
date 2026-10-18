# Limitations and roadmap

## Not built (cut for the hackathon)
| Item | Notes |
|---|---|
| Azure deployment of the app | Bicep for the base services exists; Container Apps, Cosmos DB, Key Vault wiring and App Insights are not deployed. Everything runs locally. |
| Teams / Microsoft 365 Copilot agent | Designed (summarize the plan, link to the web review screen; approval stays on the web screen). |
| Microsoft Agent Framework | The orchestrator is custom. |
| Web Bot Auth request signing | Stores accepted anonymous browse and cart in testing; stricter stores may require signing. |
| Big-retailer price check (Bing grounding) | Cut. |
| Persistence | Sessions and orders are in memory; they reset when the API restarts. |
| Authentication | The API has no user auth (see [security](security-and-responsible-ai.md)). |
| Phone ordering (SIP) | Stretch idea. |

## Known limitations
- The **demo birthday** uses a template and mock catalogs; only real-store jobs are fully dynamic.
- The mock stores implement a **simplified UCP subset** (discovery manifest plus a REST binding), not a conformance-tested SDK.
- **Pack sizes** on real stores are parsed from titles; an unknown pack size counts as 1, so some quantities are conservative.
- **Planner quality varies**: a model may pick odd or off-theme items. Keyword and avoid-list filters help, but a smarter relevance check would be better.
- The **same request can produce a different list** across sessions (stable within a session).
- **Real-store results depend on stock and region.** Some stores are skipped when they do not respond.
- **Latency**: a turn takes about 3-6 s; the first real-store plan 6-20 s.
- **English only** for speech by default; Hindi code-switching needs a separate pass.
- The agent-profile **tunnel is temporary**; use a stable HTTPS host for `agent_profile/agent-profile.json` in any shared demo.

## Next steps
1. Deploy to Azure Container Apps (infra Phase 2), move sessions to Cosmos DB, secrets to Key Vault, traces to Application Insights.
2. Publish the agent to Microsoft Teams and Microsoft 365 Copilot with a link-out approval screen.
3. Add API authentication (Entra ID) and rate limiting.
4. Implement Web Bot Auth and host the agent profile on a stable domain.
5. Stream replies into speech to cut perceived latency; add an LLM relevance check on real-store search results.
6. Add recorded real-store replays for offline demos and CI.
7. Evals with a model judge for explanation clarity; Foundry evaluations.
8. More scenarios on demo stores, memory for returning users, recurring plans, phone ordering.
