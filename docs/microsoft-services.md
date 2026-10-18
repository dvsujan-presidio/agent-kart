# Microsoft services in AgentKart

Honest status for the hackathon build. **Used** means it runs in the demo today.

| Service | Status | Where and how |
|---|---|---|
| **Microsoft Foundry** | **Used** | Hosts the OpenAI model deployment (`gpt-5.6-sol` in the demo, `gpt-5.6-luna` supported via env). Called through the `openai` SDK's `AzureOpenAI` client in `agent/app/llm.py`. Three jobs: parse what the user said (`nlu.py`), phrase replies from facts (`converse.py`), plan shopping lists for real stores (`planner.py`). Structured outputs are used for parsing and planning. |
| **Azure AI Speech** | **Used** | Speech-to-text (`en-IN`) and neural text-to-speech (`en-IN-NeerjaNeural`) inside the voice worker (`voice/worker.py`, `livekit-plugins-azure`). |
| Azure resource group / subscription | Used | The hackathon lab subscription hosts the Foundry and Speech resources. |
| Azure Bicep + `azd` | Written, **not deployed** | `infra/` provisions Foundry, Speech, Key Vault, Log Analytics, Application Insights and a budget alert. See [azure-setup.md](azure-setup.md). |
| Azure Container Apps, Cosmos DB, Key Vault, Application Insights | **Not deployed** | The app runs locally; sessions are in memory; secrets are in `.env`. |
| Microsoft Agent Framework | **Not used** | The orchestrator is custom (`agent/app/orchestrator.py`). |
| Teams / Microsoft 365 Copilot agent | **Not built** | Design: a thin agent that summarizes the plan and links to the web review screen. Approval would stay on the web screen. |
| Bing grounding / Foundry web search | **Not built** | A price-check for big retailers was cut. |

Not Microsoft but part of the story: **UCP** (the open commerce protocol that agentic checkout, including Copilot Checkout, builds on),
**LiveKit Cloud** (real-time voice rooms and agent dispatch) and **Next.js**.

## Why this fits Microsoft's direction
- The reasoning and the voice both run on Microsoft's AI platform (Foundry models, Azure AI Speech).
- The agent speaks the open commerce protocol that Copilot Checkout uses, so the same planning brain could sit behind a Microsoft surface.
- Responsible-AI choices are structural: human approval enforced in code, no model-computed numbers, family-friendly store policy,
  no payment handling on real stores. See [security-and-responsible-ai.md](security-and-responsible-ai.md).

## Positioning
"Copilot Checkout helps you buy a product. AgentKart helps you get a job done": it plans, quantifies, budgets and schedules a
complete multi-store order from one sentence, with a human approving every order.
