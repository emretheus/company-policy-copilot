# Implementation Plan — Tech Stack & Build Order

Companion to `PLAN.md` (the system design). This file is the concrete "what do I actually run" plan: tech stack, why each piece was chosen, repo layout, and a week-by-week build order matching the 4-week MVP from `PLAN.md` Section 14.

Stack choice for this project: **fully open-source / self-hosted** (no paid API dependency) — a deliberate portfolio choice: it proves the architecture doesn't depend on any one vendor, and it's runnable/demoable without anyone needing an API key.

---

## 1. Tech Stack Decisions

| Layer | Choice | Why |
|---|---|---|
| Backend language/framework | **Python + FastAPI** | Standard for AI/RAG systems, best library support, async-native (matters because retrieval + generation are I/O-bound), auto-generates OpenAPI docs which is useful for a demo. |
| LLM (generation) | **Self-hosted open-weight model via Ollama** — currently `llama3.2:3b` | No API cost, no external dependency, fully demoable offline. Ollama gives a simple local HTTP API so the rest of the code doesn't care what model is behind it — swappable later. **Must run natively, not in Docker**: Docker on macOS has no Metal GPU access, measured at ~25x slower. A 3B model was chosen over 8B purely for local demo latency; the pipeline is model-agnostic. See "Model size findings" below. |
| Embeddings | **Self-hosted embedding model via Ollama or sentence-transformers** (e.g. `nomic-embed-text` or `BAAI/bge-small-en`) | Same reasoning — no external dependency, and embedding models this size run fine on CPU, so no GPU requirement to demo the project. |
| Vector store | **Postgres + pgvector extension** | One database for vectors, relational data, AND the document graph (Section 6 of PLAN.md) — this is the "keep it simple" decision explicitly discussed in the design doc. Avoids running/justifying a second database for a 20k-document-scale system. |
| Keyword/full-text search | **Postgres native full-text search (`tsvector`/`tsquery`)** | Same database again — Postgres FTS is genuinely good enough at this scale, and it means hybrid search (vector + keyword) is just two queries against one database, not two systems to keep in sync. |
| Relational data (users, roles, permissions, doc graph edges, audit log) | **Postgres** | Same database, same reasoning — this is the one that was always going to be Postgres regardless of the RAG-specific choices. |
| ORM / DB access | **SQLAlchemy + Alembic** (migrations) | Standard, explicit, works cleanly with pgvector's SQLAlchemy integration. |
| Document parsing | **`unstructured`** library (PDF/DOCX/HTML → clean text) | Handles the three source formats in the spec (PDF, Word, wiki/HTML) with one library instead of three. |
| Auth | **Mock SSO for demo (a simple login form that lets you pick a demo user/role)**, designed so real SAML/OIDC can be dropped in later via `authlib` | The spec says "the company has an existing identity system" — building a real SSO integration isn't the interesting part of this project and isn't demoable without a real IdP. Mocking it cleanly, with the *interface* shaped like real SSO, keeps the permission logic identical either way. |
| Frontend | **Next.js (React) + TypeScript, minimal Tailwind styling** | Simple chat UI + a "sources" panel showing citations + a demo role-switcher. Doesn't need to be fancy — the backend is the point. |
| Background jobs (ingestion) | **APScheduler (in-process) for MVP**, structured so it can move to Celery/RQ later if needed | At MVP scale (one source, a handful of documents), a full task queue is overkill — a simple scheduled job is honest about the actual scale, matches the "don't over-engineer" principle from PLAN.md Section 12. |
| Containerization | **Docker Compose** (api, postgres, ollama, frontend as services) | One command to run the whole stack locally — important for a portfolio project, someone should be able to clone and run it. |
| Tracing/observability | **Structured JSON logging to start**, with trace fields matching PLAN.md Section 11 (query id, user, filter applied, retrieved chunks, verifier result) — OpenTelemetry hooks stubbed in but not fully wired for MVP | Full observability stack (Section 11) is explicitly deferred per PLAN.md Section 14; logging in the *shape* of future tracing means upgrading later doesn't require restructuring. |
| Testing | **pytest**, with a dedicated `tests/permission_tests.py` module treated as a first-class suite, not an afterthought | PLAN.md Section 10 calls out permission tests as security tests that should block deployment — worth a dedicated, clearly-named suite rather than mixed in with general unit tests. |

**Why not LangChain/LlamaIndex:** deliberately writing the retrieval/orchestration logic directly (plain Python + SQL + direct calls to the model APIs) instead of a framework. For a portfolio project, hand-rolling the permission-filtered retrieval, the conflict detection, and the verification step is *more* impressive and more debuggable than gluing framework components together — and it avoids the "I used LangChain and don't actually know what's happening under the hood" impression in an interview.

---

## 2. Repo Layout

```
company-policy-copilot/
├── PLAN.md                      # system design (already written)
├── IMPLEMENTATION.md            # this file
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entrypoint
│   │   ├── auth/                # mock SSO, JWT issuing/validation, user/role models
│   │   ├── ingestion/           # connectors, parsing, chunking, embedding, change detection
│   │   ├── retrieval/           # permission filter builder, hybrid search, rank fusion
│   │   ├── graph/               # document graph (supersedes/relates_to) queries
│   │   ├── conflict/            # version + contradiction detection
│   │   ├── generation/          # prompt construction, LLM calls, citation formatting
│   │   ├── verification/        # groundedness/faithfulness checker
│   │   ├── models/              # SQLAlchemy models
│   │   └── db/                  # session, migrations (alembic)
│   ├── tests/
│   │   ├── permission_tests.py  # first-class: every role/dept x every restricted doc
│   │   ├── retrieval_tests.py
│   │   └── golden_qa.py         # the golden question set from PLAN.md Section 10
│   └── requirements.txt
├── frontend/
│   └── (Next.js app: chat UI, sources panel, demo role-switcher)
└── seed_data/
    ├── documents/                # the example policy docs from the spec, as real files
    └── metadata.yaml             # access rules + supersedes links for seed docs (see PLAN.md "how supersedes is created")
```

---

## 3. Data Model (concrete tables)

```sql
-- users & org structure
users(id, name, email, role, department, country, manager_id)

-- documents & versions
document_families(id, title_base)                -- e.g. "remote-work-de"
documents(id, family_id, version_label, effective_date,
          supersedes_id, source_type, source_uri, content_hash, ingested_at)

-- access rules (kept simple: a JSON/rule expression per document, evaluated at query time)
document_access_rules(document_id, rule_json)      -- e.g. {"department": "HR"} or {"role": "all"}

-- chunks (this is what actually gets embedded and searched)
chunks(id, document_id, text, embedding vector(768), token_count, chunk_index)

-- graph edges (beyond supersedes, which lives on documents directly)
document_relations(from_document_id, to_document_id, relation_type)  -- 'relates_to' | 'localizes'

-- audit
query_log(id, user_id, question, filter_applied_json, retrieved_chunk_ids,
          answer, abstained, verifier_result_json, created_at)
```

`supersedes_id` living directly on `documents` (rather than a separate edge table) is a deliberate simplification — it's a 1:1 chain per family, so a column is simpler than a table; `document_relations` is the separate edge table for the many-to-many relations (`relates_to`, `localizes`) where a column wouldn't work.

---

## 4. Build Order — 4 Weeks

**Week 1 — Foundations + ingestion**
- Docker Compose skeleton: Postgres (with pgvector), Ollama, FastAPI stub, Next.js stub — confirm all four talk to each other.
- DB schema + Alembic migrations for the tables above.
- Seed data: write out the four example documents from the spec (Remote Work Policy DE 2025/2026, International Tax Policy, HR Internal Guideline) as real files, with a `metadata.yaml` defining their access rules and the `supersedes` link, by hand — this is the "how supersedes is created" answer from earlier in this conversation, applied concretely.
- Ingestion pipeline: parse → chunk → embed → store, for the seed documents. Confirm chunks + embeddings land correctly in pgvector.

**Week 2 — Auth + permission-aware retrieval**
- Mock SSO: login screen where you pick a demo user (pre-seeded users covering each role/department/country combination needed to exercise the four seed documents).
- Permission context builder: turn a logged-in user into a SQL filter predicate.
- Hybrid retrieval: vector search (pgvector `<->`) + keyword search (Postgres FTS), both permission-filtered, combined with a simple rank fusion (e.g. reciprocal rank fusion — simple, well-understood, no extra library needed).
- **Permission test suite written this week, not later** — for every seed user, assert the HR-only document never appears in results. This is the security-critical path; get it under test immediately, not as cleanup at the end.

**Week 3 — Generation, versioning, verification**
- Document graph: `supersedes` resolution (which version is "current") and the two hardcoded `relates_to` edges (remote work ↔ tax policy) per PLAN.md Section 14's MVP scope.
- Conflict detection: version conflicts resolved via the graph; flag (don't resolve) genuine contradictions.
- Prompt construction: retrieved chunks + explicit "which is current" metadata → LLM call → citation-formatted draft answer.
- Groundedness verifier: check draft claims against retrieved text (start simple — keyword/fact overlap check; upgrade to a second LLM call if time allows).
- Abstention wiring: no-results case, low-confidence case, verifier-rejection case all route to a clear "I don't know" response.

**Week 4 — Frontend, eval, polish**
- Chat UI: question box, answer with inline citation markers, expandable sources panel, demo role-switcher (so a reviewer can see the same question answered differently per role without needing real SSO).
- Golden test set: 20-30 questions (including the Turkey/25-days multi-doc example, a version-conflict question, an HR-only question asked by a non-HR user expecting abstention) — run as an automated pytest suite.
- Structured logging matching the trace shape from PLAN.md Section 11, viewable per-query (even just a simple "show trace" debug endpoint/panel is enough for a demo).
- README with setup instructions, architecture diagram (reuse PLAN.md's mermaid diagram), and a recorded/gif walkthrough of the Turkey example end-to-end.

---

## 4b. Findings from actually building it

Three things only surfaced once the system was running against a real model.
They are worth knowing because they're the kind of thing an interviewer probes
for — "what broke that you didn't anticipate?"

**1. The corpus stated rules but not the facts needed to apply them.**
The Tax Policy says "remote work outside the EU requires HR approval" but no
document anywhere says whether Turkey is in the EU. The model was left to fill
that gap from world knowledge — and hedged, producing a useless non-answer.

Fix: EU membership became structured reference data (`app/retrieval/geo.py`),
resolved deterministically and passed to the generator as a stated fact. The
general lesson: *if answering requires a fact the corpus doesn't contain,
that fact needs an owner in the system.* Leaving it to the model's world
knowledge is ungrounded reasoning wearing a RAG costume.

**2. The groundedness verifier was worse than useless at small model size.**
The original design (PLAN.md Section 9) had a second LLM call asking "is every
claim supported?" as a hard gate. In practice a 3B model rejected *correct*
answers, once producing reasoning that agreed with the draft while still
voting to reject. Every rejection is a false abstention, and a system that
refuses correct answers gets abandoned.

Fix: split the check in two. A deterministic pass asserts every number in the
answer appears in the sources — no model judgement, cannot be argued out of a
rejection, and it catches the highest-severity hallucination (a wrong figure
in a policy answer). The LLM contradiction check was narrowed and demoted to
*advisory*: recorded for observability, but non-blocking. `CONTRADICTION_CHECK_BLOCKS`
flips it back to a gate once a stronger verifier model is available.

This is the honest version of the design: the three-layer abstention story in
PLAN.md is right, but layer 3's reliability is a function of model capability,
and pretending otherwise ships false refusals.

**3. Abstention layer 1 was specified but never implemented — and it mattered.**
Without a relevance floor, "Can I expense a home office chair?" retrieved four
unrelated policies, and the model dutifully answered from them — inventing a
"Retail Credit Card Policy" that does not exist. The abstention logic couldn't
help, because from its perspective documents *had* been retrieved.

Fix: a cosine-distance floor, calibrated against the corpus rather than
guessed — on-topic questions land at 0.25–0.36, off-topic at 0.48+, so the
threshold sits at 0.42 in the gap. Keyword search is deliberately skipped when
nothing clears the floor, since it matches incidental word overlap ("expenses")
and would otherwise smuggle irrelevant text past the gate.

The broader point: **the abstention layers are not redundant.** Each catches a
different failure, and the cheapest, most deterministic one (a threshold, no
LLM involved) prevented the worst observed hallucination.

## 5. What to explicitly demo (ties back to the differentiators)

When showing this project, three moments should be front and center, because they're what separates it from a tutorial RAG app:

1. **Same question, different role** — ask "how many days can I work remotely" as a normal employee, then switch to the HR demo user and ask again. Show the HR user gets the 40-day exception mentioned and the employee doesn't — proves permission-aware retrieval is real, not decorative.
2. **The Turkey question** — shows multi-document assembly (remote work + tax policy) and version resolution (2026 overrides 2025, with the change explicitly called out) in one answer.
3. **A deliberately unanswerable question** — ask something not covered by any seed document, show the system abstains with a clear explanation instead of guessing.
