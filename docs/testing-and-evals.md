# Testing and evaluation

## Unit and integration tests: 150 passing
`make test` runs pytest over `domain/`, `contracts/`, `agent/`, `stores/` and `voice/`. No live network, models, LiveKit or Azure Speech are used.

| Area | What is checked |
|---|---|
| `domain/` | quantities and pack rounding; the **optimizer matches brute force** on 300 random cases (including free-delivery thresholds and minimum orders); trade-offs; fallback; split property tests (always sums exactly) |
| Approval gate | no token, tampered, expired, wrong basket, edit after approval, reused or superseded request, other session, hedged voice answer |
| Voice | the confirmation gate on 50+ phrases (English, Hindi in Devanagari, hedges, numbers, empty); the dialog state machine; spoken money and times |
| Stores | UCP manifest, search, cart, checkout totals, order progression, delay endpoint |
| Full flow | the whole demo story with a scripted language layer and in-process stores: questions, plan, premium cake, option, split, approval, checkout, delay, backup order |
| Conversation layer | placeholder substitution; model-written numbers, unknown placeholders and markdown are rejected or stripped |
| Real stores | fake UCP/MCP transport: discovery from the manifest, profile on every call, on-topic and in-stock filtering, pack-size parsing, **checkout tools refused**, cart failure degrades gracefully |
| Planner | validation and sizing in Python; a never-seen scenario; add and remove items by words; items no store stocks; planner failure handled |
| Addresses | saved, declined, and a new address collected piece by piece into the read-back |

## Deterministic evals: 108 scenarios, 9 metrics, all 100%
`make eval` generates scenarios (3 group sizes x 3 budgets x 3 exclusion sets x 2 flavours x 2 tiers x eggless) and runs the real pipeline against the mock stores. Output: `evals/report/index.html` and `results.csv`.

| Metric | Result |
|---|---|
| Budget compliance when feasible | 108/108 |
| No late items | 108/108 |
| Exclusions respected | 108/108 |
| Quantity sufficiency | 108/108 |
| Split sums exactly | 108/108 |
| Single currency | 108/108 |
| Optimal total vs brute force | 108/108 |
| Checkout needs approval | 108/108 |
| Edit invalidates approval | 108/108 |

## End-to-end checks (live, run by hand)
| Command | What it proves |
|---|---|
| `make demo` | the whole demo story through the API with the real model |
| `make ui-test` | the typed demo in the real web UI (headless Chromium), no console errors |
| `make ui-real-test` | the real-store flow in the UI against live stores (US exit): plan, add to carts, cart links |
| `make voice-test` | speaks the demo into a LiveKit room with Azure TTS; the worker hears it (Azure STT), replies, rejects the hedged "wait, change the cake", and places orders after the clear "yes" |
| `make probe-real` | per-category live results from the real stores |

## Measured behaviour
| Item | Observation |
|---|---|
| Turn latency, demo stores | about 3-6 s (parse + phrase + sourcing); a filler is spoken after 1.3 s on voice |
| First real-store plan | 6-20 s (planning + live searches); cached for 10 minutes |
| Cart totals vs basket | matched to the cent on stores tested; a "price differs" badge appears when a store disagrees |

## Findings that shaped the design
- Azure speech-to-text with Hindi enabled transcribed English as Devanagari, so the confirmation gate understands Devanagari yes/no words and the default is English only.
- Turns split mid-sentence on short pauses; the worker waits 1.0 s before closing a turn and the planner accumulates partial turns.
- A shared reply slot made the voice agent answer one turn late under speculative generation; each turn now awaits its own API call.
- Search is semantic (a "headlamp" query returns headbands), so results must also match keywords and an avoid list.

## What is not tested automatically
Live real-store calls, LiveKit audio and Azure Speech are exercised by the manual end-to-end commands above, not by CI, on purpose.
