# Security and responsible AI

## Guarantees enforced in code
| # | Guarantee | Where |
|---|---|---|
| 1 | **No order without approval.** `/checkout` needs a signed token bound to the current basket hash. Tokens come only from `/approve` answering a live, single-use request (90 s). No model-visible tool can call `/approve` or `/checkout`. | `agent/app/approval.py`, `orchestrator.checkout` |
| 2 | **No model decides "yes".** A spoken confirmation is judged by deterministic Python: a clear affirmative with no hedge, no change word, no number, adequate speech-to-text confidence. | `voice/confirmation.py` |
| 3 | **Edits invalidate approvals.** Any basket edit or address change cancels pending requests and tokens. A token issued for one basket cannot place another. | `approval.invalidate_session`, hash check in `verify` |
| 4 | **The read-back is the server's text**, built from the basket and spoken verbatim, never reworded by a model. | `narrate.readback`, `Reply.verbatim` |
| 5 | **Models never produce numbers.** The conversation layer may only write `{placeholders}`; a draft with its own digits, an unknown placeholder or money words is discarded for the deterministic text. | `agent/app/converse.py` |
| 6 | **Checkout re-prices first.** Before placing any order the API re-prices every store cart and aborts if any total moved. Checkout is idempotent. | `orchestrator.checkout` |
| 7 | **Real stores get carts, never orders.** The MCP client has an allowlist (search, lookup, get_product, cart tools). Checkout tools are refused before any network call. No payment details are ever sent. | `agent/app/real_stores/mcp_client.py`, tests |
| 8 | **Store data is untrusted.** Titles are sanitized and capped; store text is never put into a prompt as an instruction; the NLU never sees product text. | `ucp_client.clean_text`, `nlu.py` |
| 9 | **Planner output is validated.** Slugs, query text, keywords, store ids, rates and item counts are clamped; unknown stores are dropped. The user's words are delimited as data. | `agent/app/planner.py` |

## Threat model
| Threat | Mitigation | Residual risk |
|---|---|---|
| Model "buys" something on its own | No tool path to approve or checkout; token needs a user action | None known |
| Prompt injection via a product title | Sanitization, store text kept out of instructions, parsing and phrasing have no tools | The phrasing step sees item titles in facts; it can only emit placeholders and text |
| Model invents a price or quantity | Numbers come from Python; drafts with digits are rejected | None for numbers; wording can still be imperfect |
| Misheard "yes" or a hedged "yes, but..." | Deterministic gate; a hedge rejects; request stays single-use and expires | Speech-to-text errors could mis-transcribe a real "no" as a clear "yes" (low probability; the read-back precedes it) |
| User changes the basket after approving | Hash binding and invalidation | None known |
| Real-store price changes at cart time | Cart totals are authoritative; a "price differs" badge is shown | Final price is the store's at checkout |
| Exposure of the local machine | The tunnel serves only the public agent-profile JSON | The profile URL is public by design |
| Secrets in the repository | `.env` is git-ignored, `.env.example` has placeholders, no keys in code | Rotate keys if ever exposed |

## Privacy
- Delivery addresses go only to the **demo** stores the user approves an order with. **Real stores never receive personal data**: carts are created with a country and currency only.
- The model sees the user's words and non-sensitive facts. It does not see payment data (none is collected).
- Sessions are in memory and disappear when the API restarts. No analytics or third-party tracking.
- Audio goes browser to LiveKit Cloud to the voice worker to Azure AI Speech. Nothing is recorded by this application.

## Responsible-AI choices
- **Human in control.** Explicit approval for every purchase, with the full cart shown and read back.
- **Transparency.** Real-store totals are labelled estimates; excluded items are explained; unavailable items are reported; degraded steps show a badge.
- **Family-friendly only.** The curated store list excludes age-restricted brands (alcohol, tobacco/vape, adult supplements, adult content), and the planner is instructed to refuse such requests.
- **No scraping, no impersonation.** Real stores are reached only over UCP, with our own agent profile.
- **Respectful to merchants.** Per-store concurrency limit, backoff on 429 / `Retry-After`, cached searches.

## Secrets handling
- Local: `.env` only (git-ignored). Copy `.env.example` and fill it in. Never commit `.env`.
- Azure: store keys in Key Vault (Bicep provided); do not bake them into images.
- Set `APPROVAL_HMAC_SECRET` to a long random value; the example default is only a placeholder.

## Known gaps (be honest in review)
- The API has **no user authentication**: anyone who can reach it and knows a session id can use that session. Fine for a local demo; add Entra ID or tokens before any public deployment.
- Web Bot Auth request signing is not implemented (stores accepted anonymous browse and cart in testing).
- No rate limiting or abuse protection on the API itself.
- CORS is limited to the configured web origin.
