# Demo script (about 4 minutes)

Prepare: `make start`, open http://localhost:3000, headset on, US network exit for the real-store segment. Reset with `POST /demo/reset` between runs.
Numbers below are what the seeded data produces.

## Part 1: demo stores by voice (rupees)
| # | Say | What the audience sees and hears |
|---|---|---|
| 1 | tap **Talk to AgentKart** | The agent greets you. |
| 2 | "Help me shop for a birthday party for 10 people tomorrow evening, under three thousand rupees. I already have plates." | Short, natural questions: cake flavour, eggless, delivery address. |
| 3 | "Chocolate." "No, regular is fine." "Yes, use my saved address." | The basket appears: ₹2,665 across 2 stores. **Savings callout:** using 2 stores instead of 3 saved ₹49. PartyBazaar cups would be ₹55 cheaper but arrive too late, so they are excluded and explained. Plates are absent because you have them. |
| 4 | "Make it a premium 1.5 kg cake." | ₹3,265, ₹265 over budget. Three trade-offs, the best first: use a standard cake (₹2,965), drop banner and party hats (₹2,991). |
| 5 | "Do that one." | Back under budget at ₹2,965. |
| 6 | "Four of us are splitting this." | Shares add up exactly (₹741.25 each). |
| 7 | "Place the order." | The agent reads back the exact total, stores, arrival time and address. |
| 8 | "Wait, actually, change the cake." | **Nothing is ordered.** The gate rejected the hedge. |
| 9 | "Place the order." then "Yes, place the order." | Two orders are placed (CakeCorner, SnackMart). The screen shows approval by voice. |
| 10 | click **Simulate cake delay** | The agent speaks up: the cake is delayed; NearbyBakery can do pickup in an hour for ₹30 more, still within budget. "Yes" approves a **separate** backup order. |

Talking points: LiveKit carries the voice; Azure AI Speech does speech; the model only parses and phrases; every number, the quantities and the
approval come from deterministic, tested code.

## Part 2: real stores over UCP (dollars)
| # | Say | What happens |
|---|---|---|
| 11 | "Plan a camping weekend for 4 people leaving Friday, budget 4000 dollars." | The planner decides what to buy; the agent discovers real stores through `/.well-known/ucp`, searches them live, and shows real products with photos. "Estimate" badge, delivery "at checkout". |
| 12 | "Add a lantern." "Remove the jackets." | The list changes by words. |
| 13 | "Add it to the carts." | Real UCP carts are created. **Open cart** opens each store's own cart. The panel states that nothing has been ordered. |
| 14 | try to "just buy it" | It cannot: checkout tools are blocked in code and `/checkout` returns 403 on a real session. |

If the network is shaky, use the demo-store segment only, or `REAL_STORE_REPLAY` with recorded responses.

## Backup plan
- If voice fails, the same session continues in text with the on-screen **Approve** button.
- `make demo` prints the whole demo-store story in a terminal with the real model.
- Screenshots of every step are in [images/](images/).
