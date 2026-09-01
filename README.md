# Enterprise Policy Copilot

A permission-aware RAG system for internal company policy questions — where **access control is enforced inside retrieval, not bolted on afterwards**, versions resolve automatically through a document graph, and the system abstains instead of guessing.

The premise: in a policy assistant, a confidently wrong answer or a leaked salary document is worse than no answer at all. Everything below follows from that.

```mermaid
flowchart LR
    U["👤 Employee<br/>asks a question"] --> API["FastAPI"]
    API --> R["Permission-scoped<br/>retrieval"]
    R --> G["Answer + citations"]
    G --> V["Verification"]
    V -->|verified| A["✅ Answer with sources"]
    V -->|can't verify| AB["🚫 I don't know"]

    style A fill:#1b3a2a,stroke:#8fd19e,color:#e6e6e6
    style AB fill:#3a2f1b,stroke:#e0b34d,color:#e6e6e6
    style U fill:#161a22,stroke:#2a2f3a,color:#e6e6e6
    style API fill:#141b2c,stroke:#6ea8fe,color:#e6e6e6
    style R fill:#141b2c,stroke:#6ea8fe,color:#e6e6e6
    style G fill:#141b2c,stroke:#6ea8fe,color:#e6e6e6
    style V fill:#141b2c,stroke:#6ea8fe,color:#e6e6e6
```

---

## What makes this different from a standard RAG demo

| | Standard RAG | This system |
|---|---|---|
| **Access control** | Retrieve everything, filter or prompt afterwards | Filter applied *inside* the SQL query — unauthorized text is never fetched, never scored, never sent to the model |
| **Document versions** | All versions look equally relevant to similarity search | A `supersedes` graph resolves which version is current, deterministically |
| **Multi-document answers** | Hope the right chunks land in top-k | `relates_to` edges pull in required companion documents |
| **Hallucination** | Ask the model nicely to stay grounded | Relevance floor + deterministic numeric check + contradiction check |

---

## Architecture

```mermaid
flowchart TB
    subgraph Client["Frontend · Next.js"]
        UI["Chat UI · role switcher<br/>citations panel"]
    end

    subgraph Backend["Backend · FastAPI"]
        AUTH["Auth<br/>mock SSO → JWT"]
        PERM["Permission context<br/>role · dept · country"]
        RET["Hybrid retrieval<br/>vector + keyword"]
        GRAPH["Document graph<br/>supersedes · relates_to"]
        CONF["Conflict detection"]
        GEN["Generation<br/>citation-forced prompt"]
        VER["Verification<br/>numeric + contradiction"]
    end

    subgraph Data["Storage · PostgreSQL + pgvector"]
        VEC[("Chunks<br/>+ embeddings")]
        REL[("Users · documents<br/>access rules · edges")]
        LOG[("Query log<br/>audit trail")]
    end

    LLM["Ollama · local<br/>llama3.2 + nomic-embed"]

    UI --> AUTH --> PERM --> RET
    RET <--> VEC
    PERM <--> REL
    RET --> GRAPH --> CONF --> GEN --> VER --> UI
    GEN <--> LLM
    VER <--> LLM
    RET <--> LLM
    VER --> LOG

    style Client fill:#0b0e13,stroke:#2a2f3a,color:#9aa4b2
    style Backend fill:#0b0e13,stroke:#2a2f3a,color:#9aa4b2
    style Data fill:#0b0e13,stroke:#2a2f3a,color:#9aa4b2
```

---

## How a question flows through the system

Walking the headline case: **Anna (Employee, Germany) asks "Can I work remotely from Turkey for 30 days?"**

```mermaid
sequenceDiagram
    autonumber
    participant U as Anna · Employee
    participant API as FastAPI
    participant DB as Postgres + pgvector
    participant LLM as Ollama

    U->>API: question + JWT
    API->>API: resolve role, dept, country
    API->>DB: compute allowed document ids
    Note over API,DB: HR-only docs excluded here —<br/>before anything is scored

    API->>LLM: embed(question)
    API->>DB: vector + keyword search<br/>WHERE document_id IN (allowed)
    Note over DB: relevance floor (0.42)<br/>nothing relevant → abstain early

    API->>DB: graph expansion via relates_to
    Note over DB: pulls in International Tax Policy

    API->>API: version conflict → 2026 supersedes 2025
    API->>LLM: generate answer (excerpts + verified facts)
    LLM-->>API: draft + citations

    API->>API: numeric check — every figure in sources?
    API->>LLM: contradiction check (advisory)
    API-->>U: "20 days, not 30" + sources
```

**What Anna is told:** the current 2026 policy allows 20 days, this replaced the 30-day 2025 version, and Turkey being outside the EU means HR approval is required.

**What she is never told:** that an HR-only guideline permits 40-day exceptions. That document was excluded at step 3 — the model never saw it, so it cannot leak it.

---

## The permission boundary

The single most important design decision — where the check happens:

```mermaid
flowchart LR
    subgraph Wrong["❌ Retrieve then filter"]
        direction TB
        W1["Search all documents"] --> W2["Model sees<br/>restricted text"] --> W3["Hope it stays quiet"]
    end

    subgraph Right["✅ Filter inside the query"]
        direction TB
        R1["Compute allowed ids"] --> R2["SQL WHERE clause"] --> R3["Restricted text<br/>never leaves the DB"]
    end

    style Wrong fill:#2a1b1b,stroke:#d18f8f,color:#e6e6e6
    style Right fill:#1b2a1f,stroke:#8fd19e,color:#e6e6e6
```

One prompt injection defeats the left-hand design. The right-hand one holds because it is a database constraint, not a request to a probabilistic system. `backend/tests/permission_tests.py` asserts this under adversarial phrasing and is treated as a deployment gate.

---

## Three-layer abstention

Each layer catches a failure the others miss:

```mermaid
flowchart TB
    Q["Draft answer"] --> L1

    L1{"1 · Relevance floor<br/><i>deterministic</i>"}
    L1 -->|nothing above 0.42| STOP1["🚫 No relevant policy found"]
    L1 -->|relevant chunks| L2

    L2{"2 · Numeric check<br/><i>deterministic · hard gate</i>"}
    L2 -->|figure not in sources| STOP2["🚫 Cannot verify"]
    L2 -->|all figures grounded| L3

    L3{"3 · Contradiction check<br/><i>LLM · advisory</i>"}
    L3 --> OK["✅ Answer + citations"]

    style STOP1 fill:#3a2f1b,stroke:#e0b34d,color:#e6e6e6
    style STOP2 fill:#3a2f1b,stroke:#e0b34d,color:#e6e6e6
    style OK fill:#1b3a2a,stroke:#8fd19e,color:#e6e6e6
```

Layer 1 was the one that mattered most in practice — without it, an uncovered question ("can I expense a home office chair?") retrieved four unrelated policies and the model invented a *"Retail Credit Card Policy"* to cite. Layer 3 is advisory at the current model size because a 3B model produced false rejections; see [`docs/IMPLEMENTATION.md`](./docs/IMPLEMENTATION.md) §4b.

---

## Stack

Fully open-source and self-hosted — no API keys, runs offline.

| Layer | Choice |
|---|---|
| Backend | Python · FastAPI · SQLAlchemy |
| LLM + embeddings | Ollama — `llama3.2:3b`, `nomic-embed-text` (direct HTTP, **no LangChain**) |
| Storage | PostgreSQL + pgvector — vectors, full-text, relational data and graph edges in one database |
| Frontend | Next.js · React · TypeScript |

Writing the retrieval, conflict and verification logic directly rather than through a framework is deliberate: for this project the interesting part *is* that logic, and it stays debuggable.

---

## Running it

Postgres and the API run in Docker. **Ollama and the frontend run natively** — this is not stylistic:

- Docker on macOS cannot reach the Metal GPU, so containerized inference falls back to CPU — measured at **122s vs 4.6s** for the same generation.
- `npm install` and Next.js rebuilds over a bind mount are drastically slower than on the host.

On a Linux host with an NVIDIA GPU, use the `containerized-llm` and `containerized-ui` compose profiles instead.

```bash
# 1 · Ollama, natively (first run pulls models)
OLLAMA_HOST=127.0.0.1:11435 ollama serve &
OLLAMA_HOST=127.0.0.1:11435 ollama pull llama3.2:3b
OLLAMA_HOST=127.0.0.1:11435 ollama pull nomic-embed-text

# 2 · Postgres + API
docker compose up -d --build

# 3 · Schema and seed data
docker exec -it policy-copilot-api alembic upgrade head
docker exec -it policy-copilot-api python -m app.ingestion.seed

# 4 · Frontend
cd frontend && npm install && npm run dev
```

App → http://localhost:3000 · API docs → http://localhost:8000/docs

### Tests

```bash
docker exec -it policy-copilot-api pytest tests/ -v
```

16 tests: permission boundaries (the security gate), retrieval quality and version resolution, plus an end-to-end golden set.

---

## Try it

The UI ships with role-specific example prompts, each labelled with what it demonstrates — switching roles swaps the list.

The demo worth seeing first: ask **"Can I work remotely from Turkey for 30 days?"** as **Anna Employee**, then again as **Helena HR**. The answer changes, because retrieval itself is permission-scoped — not the presentation layer.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/PLAN.md`](./docs/PLAN.md) | System design — architecture, ingestion, RBAC/ABAC, permission-aware retrieval, versioning, conflict handling, abstention, evaluation, observability, scaling, security, and a 4-week MVP scope |
| [`docs/IMPLEMENTATION.md`](./docs/IMPLEMENTATION.md) | Tech stack decisions with rationale, repo layout, data model, build order — and §4b, three problems that only surfaced once it was running |
| [`docs/DEMO_SCENARIOS.md`](./docs/DEMO_SCENARIOS.md) | Seed documents, demo users, and the scripted walkthrough behind the UI's example prompts |
