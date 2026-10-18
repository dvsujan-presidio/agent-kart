# API reference

Base URL (local): `http://localhost:8000`. Interactive docs: `/docs` (OpenAPI). All bodies are JSON. Money is integer minor units plus a currency.

## Sessions and conversation
| Method | Path | Purpose |
|---|---|---|
| POST | `/sessions` | Start a session. Returns `session_id` and the opening `greeting`. |
| POST | `/sessions/{id}/messages` | Send a user turn `{text, channel: "web"\|"voice"}`. Returns `{reply, approval_request}`. The same endpoint serves typed and spoken turns. |
| GET | `/sessions/{id}` | Snapshot: basket, orders, history, pending approval, event count. |
| GET | `/sessions/{id}/events` | Server-sent events (supports `Last-Event-ID` / `?after=N` replay). |
| GET | `/sessions/{id}/basket` | Current basket view. |
| POST | `/sessions/{id}/basket/edit` | `{action: "apply_option", index}` or `{action: "remove", category}`. |
| POST | `/sessions/{id}/split` | `{payers}`: set the number of people splitting. Deterministic, no model. |
| GET | `/sessions/{id}/summary` | Short text, totals and a `/review/{id}` link (for a Teams surface). |

## Demo stores: approval and checkout
| Method | Path | Purpose |
|---|---|---|
| POST | `/sessions/{id}/approval-request` | Freeze the basket hash and return an `ApprovalRequest` with a server-built `readback`. |
| POST | `/sessions/{id}/approve` | `{request_id, channel, utterance?, stt_confidence?}`. For `voice`, the server runs the deterministic confirmation check. Returns a signed token. |
| POST | `/sessions/{id}/checkout` | `{token}`. Refused (403) unless the token is valid for the **current** basket hash. Re-prices every store before placing anything. Idempotent. |
| GET | `/sessions/{id}/orders` | Order statuses. |

## Real stores
| Method | Path | Purpose |
|---|---|---|
| GET | `/real/config` | Flags, enabled scenarios, whether the agent profile is reachable, `never_orders: true`. |
| POST | `/sessions/{id}/handoff` | Create a cart at each store and return `continue_url`s. Never orders. |
| GET | `/sessions/{id}/real/carts` | Current carts. |

## Voice and demo
| Method | Path | Purpose |
|---|---|---|
| POST | `/sessions/{id}/voice` | Mint a short-lived LiveKit token and dispatch the voice worker. Returns `livekit_url`, `room`, `participant_token`. |
| POST | `/demo/delay` | (demo mode only) push an order past its deadline `{session_id, store_id, hours}`. |
| POST | `/demo/reset` | (demo mode only) clear sessions and store orders. |
| GET | `/health` | Liveness. |

## Event stream
| Event | Payload | Used by |
|---|---|---|
| `session_started` | session id | web |
| `chat_message` | `{role, text, channel?, greeting?, fallback?}` | web (the chat thread, including spoken turns) |
| `basket_updated` | full basket view | web basket panel |
| `approval_requested` | `{kind: main\|backup, request_id, readback, expires_at, basket, announce?}` | web modal, voice worker |
| `approved` | `{channel, at, kind}` | web (closes modal), voice worker |
| `order_status` | order record | web order tracker |
| `fallback` | `{order_id, text, option}` | web banner, voice worker |
| `real_carts` | `{carts: [...]}` | web carts panel |
| `error` | `{message}` | web |

## Failure semantics
- `403`: no or invalid approval token, hedged or unclear spoken confirmation, expired or superseded request, basket changed since approval.
- `409`: nothing to order, checkout price changed, no real-store basket to add to carts.
- `503`: voice not configured.
