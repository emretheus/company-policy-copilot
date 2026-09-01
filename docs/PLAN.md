# Enterprise Policy Copilot — System Design

A portfolio project: an AI assistant that answers employee questions about internal company policies (HR, travel, remote work, expenses, security, etc.) by reading internal documents, respecting who is allowed to see what, and never making things up.

This document explains the whole system in plain language: what each piece does, why it exists, and what problem it solves. It's written so I can explain every decision out loud in an interview without needing notes.

---

## 0. The one-sentence pitch

> A RAG system where **access control is part of retrieval, not a filter bolted on afterward**, and where the system **knows when it doesn't know** — because in a company policy tool, a confident wrong answer or a leaked salary document is worse than no answer at all.

That's the differentiator from a "classic RAG demo." Classic RAG: embed documents, search, stuff into a prompt, generate. This system adds three things classic RAG doesn't have:

1. **Permission-aware retrieval** — the database physically cannot return a document the user isn't allowed to see.
2. **A small knowledge graph** — because "which policy is the current one" and "which policies relate to each other" is not something vector similarity can answer.
3. **A verification step after generation** — the system checks its own answer against the source text before showing it to the user, and refuses to answer if it can't back up a claim.

---

## 1. High-Level Architecture

```mermaid
flowchart TB
    U[Employee asks a question] --> GW[Login / Auth]
    GW --> ORCH[Orchestrator]
    ORCH --> QU[Understand the question<br/>break it into sub-questions if needed]
    QU --> PCTX[Figure out what this user<br/>is allowed to see]
    PCTX --> RET[Search only inside<br/>allowed documents]
    RET --> FUSE[Combine + rank results]
    FUSE --> CONF[Check for conflicting<br/>or outdated info]
    CONF --> GEN[Draft an answer<br/>with citations]
    GEN --> VER[Double-check the answer<br/>against the sources]
    VER -->|can't verify| ABST[Say "I don't know" +<br/>explain why]
    VER -->|verified| RESP[Show answer + sources]
```

**Plain-language walkthrough:**

1. User logs in → we know their identity (role, department, country, manager).
2. The question is understood and, if it touches multiple topics, split into parts.
3. We compute exactly which documents this specific user is allowed to read.
4. We search **only inside that allowed set** — not "search everything, then hide results."
5. Results are combined, and we check: is there a version conflict? A contradiction between two policies?
6. An LLM drafts an answer using only the retrieved, allowed text, with citations.
7. A second pass checks: does every sentence in the draft actually trace back to a real citation? If not, cut it or refuse.
8. User sees the final answer with clickable source references.

---

## 2. Document Ingestion — how we handle changing, messy source data

**The problem:** policies live in PDFs, Word docs, and wiki pages, scattered across departments, updated at different times, sometimes with country-specific versions, sometimes superseding older versions. New or edited documents show up continuously — this can't be a one-time import.

**How it works:**

1. **Connectors** pull documents from each source system (SharePoint, Confluence, a file share, etc.) on a schedule and also react to "file changed" webhooks/events where available. This means updates don't require a human to manually re-upload anything — a new HR PDF uploaded today is picked up automatically.
2. **Metadata extraction**, for every document, before we touch the content: who owns it, which department, which country (if any), what access level it has, effective date, and — critically — **what document it replaces, if any**. Some of this comes from the source system (folder structure, SharePoint permissions), some from a metadata sidecar/config the document owners fill in, some inferred from the document itself (e.g., "Remote Work Policy — Germany — 2026" tells us country + version from the title).
3. **Chunking**: break each document into smaller passages (a few paragraphs each) so retrieval can return precise, relevant sections instead of whole 40-page PDFs. Each chunk keeps the metadata of its parent document attached (this is what makes permission filtering possible later).
4. **Embedding**: turn each chunk into a vector (a list of numbers representing its meaning) so we can later search by meaning, not just keyword.
5. **Change detection**: when a document is re-ingested, we hash its content. If unchanged, skip re-processing (saves cost). If changed, we create a **new version** rather than overwriting — the old version doesn't disappear, it just gets marked as superseded (see Section 7, Versioning).
6. **Dead-letter queue**: if a document fails to parse (corrupted PDF, weird formatting), it goes into a review queue instead of silently failing — someone gets notified instead of the system just pretending that document doesn't exist.

**Why not just re-scan everything nightly?** At 20,000 documents, full re-processing is wasteful and slow, and it means changes take up to 24 hours to show up. Event-driven ingestion (webhook says "this file changed") plus a nightly full sync as a safety net (catches anything the webhook missed) gives near-real-time updates without the cost of constant full re-indexing.

---

## 3. Data Model & Storage — what we actually store and where

Three storage systems, each doing the job it's good at. This is deliberate — trying to force one database to do all three jobs is where a lot of RAG systems get messy.

| Store | What it holds | Why this store |
|---|---|---|
| **Vector DB** | Chunk text + embedding + metadata (doc id, department, country, access roles, version, effective date) | Fast "find text similar in meaning to this question," with metadata filtering built in |
| **Keyword index (BM25/full-text)** | Same chunks, indexed for exact keyword match | Vector search is bad at exact terms — policy names, numbers ("30 days"), acronyms. Keyword search catches what meaning-search misses. Combining both ("hybrid search") is standard practice, not extra complexity. |
| **Relational DB (Postgres)** | Users, roles, departments, document ownership, permission rules, audit logs, evaluation results | This is structured, relational data (who reports to whom, who owns what) — a real database with proper transactions and constraints is the right tool, not a vector store. |
| **Document graph** (can live inside Postgres as edges, doesn't need a separate exotic database) | Relationships: "Doc A supersedes Doc B", "Doc A is the Germany version of base policy X", "Doc A references Doc B" | See Section 6 — this is what lets us answer version and multi-document questions correctly. |

**Why not one database for everything?** Because vector similarity search, exact keyword match, relational permission logic, and graph traversal are four genuinely different query patterns. Using the right specialized tool for each is simpler to reason about and debug than forcing everything through one system's query language.

---

## 4. Authentication & Role-Based Access (RBAC) — the part that matters most

**The core requirement:** an HR-only salary document must never be readable by a random employee, even indirectly through a generated answer.

**How identity works:**
- User logs in via the company's existing identity system (SSO / SAML / OAuth — whatever they already use, we don't build our own login).
- On login we get: user id, role (Employee / Manager / HR / Finance Admin / Legal), department, country, and manager relationship (who they report to, who reports to them).

**How access rules work:**
Every document, at ingestion time, gets tagged with an **access policy** — plain rules like:
- "Visible to: all employees" (General Travel Policy)
- "Visible to: department = HR" (Salary Bands)
- "Visible to: department = Finance, OR role = Manager" (Finance Policies)
- "Visible to: owner = this specific employee, OR their direct manager, OR HR" (Performance Documents — this one is per-document, not per-department, since it depends on *who the employee is*)

This is a mix of **RBAC** (rules based on role/department — simple, most documents) and a small amount of **ABAC** (attribute-based — rules based on relationships like "is this person's manager," needed for the performance-document case). Pure RBAC can't express "only this specific employee's manager" — that's a relationship, not a role — so we need the attribute-based layer for that minority of cases.

**Where the check happens — this is the important design decision:**
The permission check happens **before and during retrieval**, not after generation. Concretely: when we search the vector database, the search query includes a filter like `department IN (user's allowed departments) OR owner_id = user.id OR ...`. The database itself refuses to return chunks that don't match. The LLM never sees unauthorized text — it's not that we ask the LLM to "please don't mention it," the text is physically never sent to it.

**Why this matters over "generate then filter":** if you retrieve everything and only filter or instruct the LLM afterward, you're one prompt-injection or one model mistake away from leaking a salary figure. Filtering at the database query level is a hard boundary, not a request to a probabilistic system.

---

## 5. Permission-Aware Retrieval — walking through the example

Question: **"Can I work remotely from Turkey for 30 days?"** — asked by a normal Germany-based Employee (not HR).

1. **Auth**: we know this user is `role=Employee, department=Engineering, country=DE`.
2. **Permission context**: build the filter — this user can see documents where `access includes "all employees"` AND (`country = DE` OR `country = none/global`). They do **not** get documents tagged `HR only`.
3. **Query understanding**: the question implies two topics — (a) how many days can I work abroad, (b) are there country-specific rules for Turkey (tax/approval). Decomposed into two retrieval calls.
4. **Retrieval with filter applied**:
   - Search finds "Remote Work Policy Germany 2025" (30 days) and "Remote Work Policy Germany 2026" (20 days) — both pass the permission filter (all employees, country DE).
   - Search finds "International Tax Policy" (remote work outside EU needs HR approval) — passes filter (all employees, no country restriction, Turkey is outside EU).
   - Search finds "HR Internal Guideline" (exceptions up to 40 days) — this chunk is tagged `HR only`. **The database filter excludes it before it's even scored for relevance.** The employee's retrieval results never contain it. This is the point of Section 4 — it's enforced here, structurally, not by asking the model to be discreet.
5. **Conflict detection**: two versions of the same policy (30 days vs 20 days) are found. The doc graph (Section 6) tells us 2026 supersedes 2025 → the current answer is 20 days, and this gets flagged explicitly rather than silently picking one.
6. **Generation**: the model is given only the retrieved, authorized chunks and asked to answer using only that text, with citations.
7. **Verification**: check that "20 days" and "HR approval required for outside-EU" are both directly supported by the retrieved text. They are → answer passes.
8. **Final answer shown to user**:
   > "Under the current Remote Work Policy (Germany, 2026), you may work abroad for up to 20 days — this replaces the 2025 version which allowed 30 days. Since Turkey is outside the EU, the International Tax Policy requires HR approval for this arrangement. [Sources: Remote Work Policy Germany 2026, International Tax Policy]"

   Note what's *not* in the answer: the 40-day HR exception. The employee is never told it exists, because they're not authorized to see it — this isn't the system being cagey, it genuinely never retrieved that text.

---

## 6. Why a Knowledge Graph — the question interviewers will ask

**The naive assumption:** "just embed everything and do similarity search."

**Where that breaks:**
- Similarity search has no concept of "this document is old, use the other one instead." Both the 2025 and 2026 remote work policies talk about the same topic in nearly identical language — they'll both score as highly relevant. Vector similarity literally cannot tell you which one is *current*.
- Similarity search has no concept of "these two documents are both needed together" for questions like the Turkey/25-days example. It can only tell you "these chunks are semantically close to the query," not "these documents form a required combination."
- Similarity search doesn't know a German remote-work policy and a French remote-work policy are "the same policy, localized," versus two unrelated documents that happen to use similar words.

**What the graph actually is:** nothing exotic — a small table of documents and a small table of typed edges between them:
- `supersedes` (2026 version → supersedes → 2025 version)
- `localizes` (Germany version → localizes → base Remote Work Policy)
- `relates_to` (Remote Work Policy → relates_to → International Tax Policy)

This can literally live as two extra tables in the same Postgres database — "knowledge graph" sounds heavier than it is. It does not require a dedicated graph database at this scale (20,000 documents, a handful of relationship types). A dedicated graph DB (Neo4j etc.) would be over-engineering here; a few relational tables with indexes do the job.

**What it buys us:**
- Version resolution: "always prefer the document with no outgoing `supersedes` edge pointing *away* from it" (i.e., the newest in the chain) as the default answer, while still being able to say "this replaced an older version that said X."
- Multi-document assembly: when a query touches Remote Work Policy, walk its `relates_to` edges to also pull in International Tax Policy automatically, rather than hoping pure similarity search happens to surface both.

This is the single most defensible "not classic RAG" talking point in an interview — it directly solves the versioning and multi-document requirements from the spec, and it's *why* the system gets version conflicts right instead of guessing.

---

## 7. Document Versioning

- Every ingested document gets a version row: `document_family_id` (stable across versions), `version_id`, `effective_date`, `superseded_by` (nullable).
- Old versions are **never deleted** — they stay searchable (for audit/history questions like "what was the policy in 2025?") but are excluded from "what's the current rule" answers by default.
- The **default retrieval behavior** is: prefer the current (non-superseded) version. If the user's question is explicitly historical ("what was the policy last year"), the query understanding step detects that and retrieves the old version on purpose.
- When both an old and current version are retrieved together (as in the Turkey example, to show what changed), the generator is explicitly told which one is current — this is metadata passed alongside the text, not something the model has to infer.

---

## 8. Conflicting Source Handling

Two kinds of conflict, handled differently:

1. **Version conflicts** (same policy, different point in time) — resolved deterministically using the graph's `supersedes` chain, as above. Not really a "conflict" once you have version metadata — it's just "use the current one, mention the change if relevant."
2. **Genuine contradictions** (two *current*, unrelated documents disagree — e.g., a country policy and a corporate-wide policy give different numbers, and neither supersedes the other). These can't be resolved automatically without guessing. The conflict detector flags this case, and the answer explicitly surfaces both, e.g.:
   > "I found conflicting guidance: the Corporate Travel Policy says X, while the France Travel Addendum says Y. I'd recommend confirming with HR — I don't want to guess which takes precedence."

   This is safer than silently picking one, and it's an explicit non-goal to have the LLM "decide" precedence when the documents themselves don't define it — that's a policy question for humans, not a language-modeling question.

---

## 9. Abstention — knowing when to say "I don't know"

Three separate safety nets, because relying on just one (e.g., just "trust the LLM to say I don't know") isn't reliable enough:

1. **Retrieval-level**: if the search returns nothing above a relevance-confidence threshold, don't even attempt generation — go straight to "I couldn't find relevant policy documents for this question."
2. **Generation-level prompting**: the model is explicitly instructed to only answer from provided text and to say so if the text doesn't cover the question — this alone is not trustworthy (models still hallucinate under instruction), but it reduces the load on the next step.
3. **Post-generation verification (the real backstop)**: a separate check — either a second LLM call or a lighter classifier — takes each factual claim in the draft answer and checks whether it's actually supported by the retrieved chunks (this is sometimes called a "groundedness" or "faithfulness" check). Unsupported claims are stripped or the whole answer is replaced with an abstention message. This is the step that actually enforces "avoid hallucinating," rather than just hoping the model behaves.

**Why three layers instead of one:** each layer catches a different failure mode — no results at all, the model ignoring instructions, or the model subtly embellishing a real citation with an unsupported detail. A single check misses at least one of these.

---

## 10. Evaluation Strategy — how we know it's actually working

The spec explicitly asks for continuous measurement of reliability — this can't be "we tested it once before launch."

- **Golden test set**: a curated set of real questions (including the Turkey/remote-work example) with known-correct answers and known-correct citations, covering: single-document questions, multi-document questions, version-conflict questions, and questions that *should* be refused (either no relevant info, or the user isn't authorized). Run automatically on every change to the ingestion pipeline, prompts, or retrieval logic.
- **Permission tests specifically**: automated tests that log in as each role and department combination and confirm forbidden documents never appear in retrieval results or citations — this is a security test, not just a quality test, and it should block deployment if it fails.
- **Groundedness/citation accuracy on live traffic**: sample a percentage of real answers, check whether every claim traces to a cited source (can be automated with an LLM-as-judge, spot-checked by humans periodically).
- **User feedback loop**: thumbs up/down plus "was this correct/helpful" on real answers, routed into a review queue — this is the main way we catch things the golden set didn't anticipate.
- **Retrieval quality metrics** (independent of the final answer): did the right document even get retrieved in the top-k results, measured against the golden set — separates "we found the right info but explained it badly" from "we never found the right info at all."

---

## 11. Monitoring & Observability

The goal isn't "have dashboards" — it's to be able to answer three specific questions at any time: *is the system telling the truth, is it leaking anything it shouldn't, and is it fast/cheap enough.* Each metric below maps to one of those.

**A. Per-query trace (the raw data everything else is built from)**
For every single question asked, log as one linked record:
- who asked it (user id, role, department, country) and the permission filter that was computed for them
- exactly which document chunks were retrieved, and which were excluded by the permission filter
- what the model generated, and what the groundedness verifier stripped or flagged
- final answer shown, latency of each stage (retrieval / generation / verification), token cost

Without this trace, none of the metrics below can be debugged — a dashboard number going wrong is useless if you can't click into *which query* caused it.

**B. "Is it telling the truth" — reliability metrics**
- **Abstention rate**: % of queries answered with "I don't know." Track as a trend line, not a single number. A sudden *spike* usually means ingestion broke (documents stopped updating, embeddings stale) or a source system went down — investigate as an incident. A sudden *drop* is also worth checking — it can mean the groundedness check got looser than intended and is letting ungrounded answers through.
- **Groundedness/verifier-rejection rate**: % of draft answers where the verifier stripped or rejected at least one claim. This is the system catching itself — track it, don't just discard the rejected drafts. A rising trend means the generator's prompting or retrieval quality is degrading upstream.
- **Retrieval hit rate against the golden set**: of the golden test questions (Section 10), % where the correct source document appeared in the top-k retrieved results. This isolates "did we find the right info" from "did we explain it well" — if this number drops after a pipeline change, the bug is in retrieval, not generation.

**C. "Is it leaking anything" — security metrics (specific to this system, not generic RAG)**
- **Permission-filter integrity check**: an automated job that periodically re-runs the golden permission tests (Section 10) in production, not just in CI — confirms that, right now, an Employee query genuinely cannot retrieve an HR-only chunk. Alert immediately (page someone) on any failure — this is the one metric in this whole system that should never silently degrade.
- **Cross-boundary retrieval attempts**: log (not block — the filter already blocks it) every time a query's *unfiltered* similarity search would have surfaced a document the user isn't authorized for, before the permission filter removes it. A rising count here isn't a breach by itself (the filter caught it), but it's a signal worth watching — e.g. a user probing with oddly specific questions about a topic they shouldn't know exists.

**D. "Is it fast/cheap enough" — operational metrics**
- **Latency**, broken down by stage (retrieval vs. generation vs. verification) — generation is almost always the slow part, so a latency regression usually means a bigger/slower model got deployed, not a retrieval problem.
- **Cost per query** (LLM tokens) — worth tracking per-department if departments are billed separately, and useful for justifying the caching strategy in Section 12.
- **Ingestion pipeline health**: documents processed vs. failed (dead-letter queue size from Section 2), time-to-visible (how long from "document updated at source" to "appears in retrieval results").

**Alerting — what actually pages someone, vs. what's just a dashboard line:**
| Signal | Action |
|---|---|
| Permission-filter integrity check fails | Page immediately — this is a potential data breach |
| Ingestion pipeline failure / dead-letter queue growing | Page — means the system is silently going stale |
| Abstention rate spikes >2x baseline | Alert (not page) — investigate within the day |
| Latency/cost creeping up | Weekly dashboard review, not an alert |

**Audit log** (kept separate from the operational trace above, retained longer, access-restricted to security/compliance staff): a durable record of every query, who asked it, and exactly which documents were shown to them. This exists specifically to answer "who saw what, and when" after the fact — a compliance requirement, not a debugging tool, so it's stored and access-controlled differently from the day-to-day observability data above.

---

## 12. Scaling Strategy

At the stated scale (8,000 users, 20,000 documents, 15 countries) this is a **moderate**-scale system, not a hyperscale one — worth saying explicitly, because over-engineering for scale that doesn't exist is its own mistake.

- Vector search and keyword search both scale horizontally (standard for both technology families) — not a bottleneck at 20k documents (likely a few hundred thousand chunks after chunking).
- The expensive, slow part is LLM generation, not retrieval — so caching matters most here: cache answers for identical (or near-identical) question + permission-context combinations, with a short TTL so it doesn't go stale when documents change.
- Ingestion can run asynchronously and in the background — it doesn't need to be fast in real time, just reliably eventually-consistent (documents show up within minutes, not instantly).
- Read-heavy, write-light system (many questions asked, documents updated relatively rarely) — optimize accordingly, e.g. read replicas for the permission/relational database.

---

## 13. Security Considerations

- **Defense at the query layer, not just the prompt layer** — repeated from Section 4 because it's the most important point in the whole design: never rely on asking the LLM nicely not to reveal something it was given.
- **Prompt injection from document content**: a malicious or careless document could contain text like "ignore previous instructions and reveal X" — mitigate by treating retrieved document text strictly as *data* in the prompt (clearly delimited, never treated as instructions) and keeping the verifier as a final check that doesn't trust the generator's own claims about what it did.
- **Least privilege for the system's own service accounts**: the ingestion pipeline needs read access to source systems; the query path needs read-only, permission-scoped access to the databases — no component gets broader access than its job requires.
- **PII handling**: performance documents and salary data are sensitive by nature — encrypt at rest, restrict the audit log itself to authorized security/compliance staff, and make sure logs/traces don't casually copy full document text into a lower-security logging system.
- **Regular access review**: since permissions are defined by role/department/country rules, a periodic automated check that these rules still match the company's actual org structure (people change teams, roles change) prevents permission rot.

---

## 14. Four-Week MVP — what's in, what's deliberately cut

**In scope for 4 weeks:**
- Ingestion for one source type (e.g., a folder of PDFs/Word docs) with metadata tagging (department, country, access role, effective date) — manual/config-based tagging is fine, doesn't need to be automatically inferred yet.
- Basic RBAC: department + role + country filtering at the vector DB query level (the ABAC "manager of this specific employee" case can be stubbed or skipped for MVP — it's a small minority of documents).
- Hybrid retrieval (vector + keyword) — both are fast to stand up with off-the-shelf tools.
- Simple versioning: a `superseded_by` field, manually set at ingestion — the full graph with multiple edge types can wait.
- Generation with forced citations + a basic groundedness check (even a simple "does this sentence's key facts appear in the source text" check is enough to start).
- A small golden test set (20-30 questions) covering the core scenarios, run manually or in CI.
- Basic tracing/logging so you can see what was retrieved and why for any given answer.

**Deliberately deferred:**
- The full multi-edge-type knowledge graph (`relates_to`, `localizes`) — MVP hardcodes the couple of known document relationships (e.g., remote work ↔ tax policy) rather than building general graph traversal.
- Multiple source connectors (SharePoint + Confluence + email, etc.) — one source is enough to prove the architecture.
- Automated event-driven ingestion — a manual/scheduled batch re-ingest is fine to start; real-time webhook ingestion is a later optimization, not a correctness requirement.
- The ABAC "manager-of" and per-document ownership permission cases — real but rare; hardcode or skip for MVP, build properly once the core RBAC path is proven.
- Full observability stack (dashboards, alerting) — basic structured logs are enough to debug during MVP; proper dashboards come once there's real traffic to look at.
- LLM-as-judge automated evaluation at scale — manual review of the golden set is enough for 4 weeks; automate once the question set is stable.
- Conflict detection for *genuine* (non-version) contradictions — rare enough in a small MVP document set that it can be handled by noting "multiple sources found" without a dedicated detection stage yet.

**Why this cut line:** everything kept in scope directly proves the three differentiating claims (permission-aware retrieval, correct versioning, no hallucination) on a small document set. Everything deferred is about *scale* or *breadth of coverage*, not about whether the core idea works — which is the right thing to prove first, and the right thing to be able to explain clearly when asked "what would you build first and why."
