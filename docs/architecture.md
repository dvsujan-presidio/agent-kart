# Architecture

Every diagram is a rendered image in [diagrams/](diagrams/) with its [Mermaid](https://mermaid.js.org/) source in a collapsible block (so it also renders natively on GitHub). The code paths that implement each one are named under it.

## 1. System context

![system context](diagrams/01-system-context.png)

<details><summary>Mermaid source</summary>

```mermaid
flowchart TB
    user([Person])
    subgraph client[Browser]
        web[Next.js web app<br/>chat, live basket, approval modal]
    end
    subgraph lk[LiveKit Cloud]
        room[(Voice room<br/>one per session)]
    end
    subgraph runtime[AgentKart runtime]
        worker[Voice worker<br/>LiveKit Agents]
        api[AgentKart API<br/>FastAPI]
        profile[Agent profile server<br/>public JSON only]
    end
    subgraph azure[Microsoft Azure]
        speech[Azure AI Speech<br/>STT and TTS]
        foundry[Microsoft Foundry<br/>OpenAI model]
    end
    subgraph stores[Stores over UCP]
        demo[Demo stores x4<br/>REST, INR]
        real[Real stores<br/>MCP, USD]
    end

    user -- voice or typing --> web
    web -- REST + SSE --> api
    web -- WebRTC audio --> room
    room <--> worker
    worker -- user turns, events --> api
    worker -- STT and TTS --> speech
    api -- parse, phrase, plan --> foundry
    api -- catalog, cart, checkout --> demo
    api -- search_catalog, create_cart --> real
    real -. fetches agent profile .-> profile
```

</details>

Code: `web/`, `voice/worker.py`, `agent/app/main.py`, `agent/app/llm.py`, `stores/server.py`, `agent/app/real_stores/`, `agent_profile/serve.py`.

## 2. API components

![api components](diagrams/02-api-components.png)

<details><summary>Mermaid source</summary>

```mermaid
flowchart TB
    routes[main.py<br/>routes, SSE, voice token]
    orch[orchestrator.py<br/>one brain for web and voice]
    nlu[nlu.py<br/>LLM: text to structured TurnParse]
    conv[converse.py + facts.py<br/>LLM: facts to natural reply<br/>numbers only via placeholders]
    planner[planner.py<br/>LLM: any request to item specs]
    pipe[pipeline.py<br/>source, filter, optimize, options]
    domain[domain/<br/>quantities, optimizer, tradeoffs,<br/>fallback, split]
    gate[approval.py<br/>signed token bound to basket hash]
    vconf[voice/confirmation.py<br/>deterministic yes/no]
    ucp[ucp_client.py<br/>demo stores]
    rs[real_stores/<br/>mcp_client + service]
    track[tracker<br/>poll orders, fallback]
    sess[(session.py<br/>in-memory state + event log)]

    routes --> orch
    orch --> nlu
    orch --> conv
    orch --> planner
    orch --> pipe
    pipe --> domain
    pipe --> ucp
    orch --> rs
    rs --> domain
    orch --> gate
    gate --> vconf
    orch --> track
    track --> domain
    orch --> sess
    routes --> sess
```

</details>

The three boxes that call a model (`nlu`, `converse`, `planner`) never compute money or quantities. `domain/` is pure Python with no network or model access.

## 3. One conversational turn

![conversational turn](diagrams/03-conversational-turn.png)

<details><summary>Mermaid source</summary>

```mermaid
sequenceDiagram
    actor U as Person
    participant S as Web or voice worker
    participant O as Orchestrator
    participant N as NLU (LLM)
    participant P as Pipeline + domain (Python)
    participant C as Converse (LLM)

    U->>S: "make it a premium 1.5 kg cake"
    S->>O: POST /sessions/{id}/messages
    O->>N: history + known state
    N-->>O: TurnParse (intent=edit, cake_tier=premium, cake_kg=1.5)
    O->>O: apply updates to PlanState
    O->>P: build_plan(state)
    P-->>O: basket, options, notes (all numbers from Python)
    O->>C: situation + facts + placeholder NAMES
    C-->>O: "That's {over} over your {budget}. Option one: {opt1_title}..."
    O->>O: validate draft (no digits, known placeholders), substitute values
    O-->>S: reply text
    O-->>S: SSE basket_updated, chat_message
```

</details>

If the draft contains its own digits, an unknown placeholder, or the call fails, the deterministic text from `narrate.py` is used instead.

## 4. Approval gate and spoken confirmation

![approval gate sequence](diagrams/04-approval-gate-sequence.png)

<details><summary>Mermaid source</summary>

```mermaid
sequenceDiagram
    actor U as Person
    participant W as Voice worker (dialog state machine)
    participant A as API
    participant G as Approval gate
    participant D as Demo stores

    U->>W: "place the order"
    W->>A: message
    A->>G: create_request(basket_hash, readback)
    G-->>A: ApprovalRequest (90 s, one use)
    A-->>W: readback text (built in Python)
    W-->>U: speaks the readback verbatim, then enters AWAIT_CONFIRM
    U->>W: "yes, place the order"
    Note over W: this turn is NOT sent to any LLM
    W->>A: POST /approve (utterance, channel=voice)
    A->>G: approve() runs deterministic is_confirmed(utterance)
    alt clear yes, hash matches, not expired
        G-->>A: signed token (session, hash, request, exp)
        A-->>W: token
        W->>A: POST /checkout (token)
        A->>G: verify(token, current basket hash)
        A->>D: cart (re-price) then checkout per store
        D-->>A: orders
        A-->>W: orders
        W-->>U: "Done. I've placed 2 orders..."
    else hedged ("wait, change the cake"), expired, or basket changed
        G-->>A: refused (403)
        W-->>U: "No problem, nothing is ordered yet..." and the turn is handled normally
    end
```

</details>

The same gate serves the on-screen **Approve** button (`channel: web`). Any basket edit or address change invalidates pending requests.

![voice dialog state](diagrams/05-voice-dialog-state.png)

<details><summary>Mermaid source</summary>

```mermaid
stateDiagram-v2
    [*] --> GATHER
    GATHER --> AWAIT_CONFIRM: reply carries an approval request
    AWAIT_CONFIRM --> GATHER: clear yes, token issued, order placed
    AWAIT_CONFIRM --> GATHER: hedged answer or timeout, nothing ordered
    GATHER --> AWAIT_CONFIRM: server pushes a backup approval request
```

</details>

Code: `agent/app/approval.py`, `voice/confirmation.py`, `voice/dialog.py`, `agent/app/orchestrator.py` (`checkout`).

## 5. Real stores over UCP: search, cart, handoff

![real stores ucp flow](diagrams/06-real-stores-ucp-flow.png)

<details><summary>Mermaid source</summary>

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant PL as Planner (LLM)
    participant R as Real-store service
    participant M as Store (UCP over MCP)
    participant PR as Agent profile (public URL)
    actor U as Person

    O->>PL: goal, group size, store menu (ids + what each covers)
    PL-->>O: items: query, keywords, stores, sizing rule
    O->>O: validate and size in Python (ceil(rate x people))
    R->>M: GET /.well-known/ucp (apex, then www)
    M-->>R: manifest (MCP endpoint, capabilities)
    R->>M: tools/call search_catalog (meta.ucp-agent.profile)
    M->>PR: fetch profile (cache-control public)
    M-->>R: products, variants, prices, stock
    R->>R: keep on-topic, in-stock, cheapest variant, parse pack size
    O->>O: optimize (same code as demo), unknown fees = estimate
    U->>O: "add to carts"
    R->>M: tools/call create_cart
    M-->>R: cart id, totals, continue_url
    O-->>U: Open cart buttons (user pays on the store)
    Note over R,M: Only an allowlist of tools is callable (search, lookup, get_product, cart). Checkout tools are refused in code.
```

</details>

Code: `agent/app/real_stores/mcp_client.py` (allowlist), `agent/app/real_stores/service.py`, `agent/app/planner.py`.

## 6. Dynamic planning (real stores)

![dynamic planning](diagrams/07-dynamic-planning.png)

<details><summary>Mermaid source</summary>

```mermaid
flowchart LR
    req["Request: 'movie night for 5 kids, $250'"] --> nlu[NLU: scenario, goal summary, people, budget]
    nlu --> plan[Planner LLM: items, queries, keywords, stores, sizing rules]
    plan --> val[Validate in Python: slugify, clamp rates, drop unknown stores, cap items]
    val --> size[Size in Python: need = ceil rate x people]
    size --> search[Search chosen stores over UCP, in parallel, cached 10 min]
    search --> filt[Filter: on-topic keywords, avoid list, in stock, cheapest variant, pack size]
    filt --> opt[Exact optimizer: cheapest valid basket]
    opt --> out[Basket, trade-offs if over budget, notes for items not found]
    edit["'add a lantern' / 'remove the blankets'"] --> val
```

</details>

## 7. Delay, fallback and backup order

![delay fallback backup](diagrams/08-delay-fallback-backup.png)

<details><summary>Mermaid source</summary>

```mermaid
sequenceDiagram
    participant T as Tracker (background)
    participant D as Demo store
    participant F as domain.find_fallback
    participant G as Approval gate
    actor U as Person

    loop every few seconds
        T->>D: GET /orders/{id}
    end
    D-->>T: status delayed, ETA after deadline minus buffer
    T->>F: delayed line + all offers (incl. pickup-only store)
    F-->>T: cheapest in-time replacement, cost, within budget?
    T->>G: new approval request for the backup basket
    T-->>U: spoken and on-screen alert with read-back
    U->>G: "yes" (own approval, own token)
```

</details>

## 8. Data model (shared contracts)

![data model](diagrams/09-data-model.png)

<details><summary>Mermaid source</summary>

```mermaid
erDiagram
    GOAL ||--o{ LISTITEM : plans
    LISTITEM ||--o{ OFFER : "matched by category"
    OFFER }o--|| STORETERMS : "store fees"
    BASKET ||--|{ BASKETLINE : contains
    BASKETLINE }o--|| OFFER : buys
    BASKET ||--o{ TRADEOFF : "options when over budget"
    BASKET ||--o| APPROVALREQUEST : "frozen by hash"
    APPROVALREQUEST ||--o| APPROVAL : answered
    BASKET ||--o{ REALCART : "real stores: one per store"
    BASKET {
        int total_minor
        string currency
        bool total_is_estimate
        string hash
    }
    OFFER {
        string store_id
        string variant_id
        int price_minor
        datetime eta
        bool in_stock
    }
    APPROVAL {
        string channel "web or voice"
        string token "HMAC signed"
    }
```

</details>

Money is always integer minor units plus a currency. The basket `hash` is a SHA-256 over lines, fees, discounts, total and currency (`contracts/hashing.py`).

## 9. Deployment

![deployment](diagrams/10-deployment.png)

<details><summary>Mermaid source</summary>

```mermaid
flowchart LR
    subgraph today[Today: runs on a laptop]
        a1[make start] --> a2[4 mock stores :8201-8204]
        a1 --> a3[API :8000]
        a1 --> a4[Web :3000]
        a1 --> a5[Voice worker]
        a1 --> a6[Profile server :8300 + tunnel]
    end
    subgraph azure[Azure resources in use]
        f[Foundry model]
        s[AI Speech]
    end
    subgraph target[Designed, not deployed: infra/ Bicep]
        c[Container Apps x7]
        k[Key Vault]
        d[Cosmos DB serverless]
        i[Application Insights]
    end
    a3 --> f
    a5 --> s
    today -. same containers .-> target
```

</details>
