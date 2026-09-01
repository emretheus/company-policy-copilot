# Demo Scenarios & Seed Documents

Companion to `PLAN.md` and `IMPLEMENTATION.md`. This is the concrete content to seed the system with, and the exact script to run when demoing it — both for building the golden test set (`PLAN.md` Section 10) and for showing the project live.

---

## 1. Seed Documents (full text, short and realistic)

Store these as actual files under `seed_data/documents/`, one per file, with the metadata below in `seed_data/metadata.yaml`.

### Doc 1 — Remote Work Policy — Germany — 2025
```
Title: Remote Work Policy (Germany)
Version: 2025
Effective: 2025-01-01

Employees based in Germany may work remotely from abroad for up to 30 days
per calendar year. Manager approval is required before departure. Employees
must remain reachable during normal working hours and ensure a stable
internet connection.
```
`family: remote-work-de` · `access: all employees` · `country: DE`

### Doc 2 — Remote Work Policy — Germany — 2026
```
Title: Remote Work Policy (Germany)
Version: 2026
Effective: 2026-01-01
Supersedes: Remote Work Policy (Germany) 2025

Employees based in Germany may work remotely from abroad for up to 20 days
per calendar year. This is a reduction from the previous 30-day allowance,
introduced to align with updated tax and social security compliance
requirements. Manager approval is required before departure.
```
`family: remote-work-de` · `access: all employees` · `country: DE` · `supersedes: remote-work-de-2025`

### Doc 3 — International Tax Policy
```
Title: International Tax Policy
Effective: 2024-06-01

Working remotely from a country outside the European Union may create tax
and social security obligations for both the employee and the company.
Any remote work arrangement outside the EU requires prior written approval
from HR, regardless of duration. Remote work within the EU does not require
this additional approval.
```
`access: all employees` · `country: none (global)` · `relates_to: remote-work-de`

### Doc 4 — HR Internal Guideline: Remote Work Exceptions
```
Title: HR Internal Guideline — Remote Work Exceptions
Effective: 2026-01-01
Access: HR only

Exceptions to the standard remote work duration limit may be approved by HR
on a case-by-case basis, for up to 40 days per calendar year, in situations
such as family emergencies or approved sabbaticals. Exception requests must
be submitted through the HR case management system and are not publicly
advertised to employees.
```
`access: HR only`

### Doc 5 — General Travel Policy (extra doc, for a clean single-source answer + for a no-conflict baseline)
```
Title: General Travel Policy
Effective: 2023-01-01

All business travel must be booked through the company's approved travel
portal. Employees are entitled to economy class for flights under 6 hours
and business class for longer flights. Travel expenses must be submitted
within 14 days of return.
```
`access: all employees`

### Doc 6 — Salary Bands (extra doc, purely to prove strict department-based denial with no country/version complexity)
```
Title: Salary Bands FY2026
Access: HR only

[salary tables omitted from demo — content irrelevant, existence/access is the point]
```
`access: HR only`

Docs 5 and 6 exist purely to broaden the test matrix beyond the remote-work family — 5 proves a clean single-document answer with no conflicts involved, 6 proves department-based denial that has nothing to do with country/version logic (a different code path than the HR-only exception doc).

---

## 2. Demo Users (for the role-switcher)

| Name | Role | Department | Country | Manager |
|---|---|---|---|---|
| Anna Employee | Employee | Engineering | DE | Mark Manager |
| Mark Manager | Manager | Engineering | DE | — |
| Helena HR | HR | HR | DE | — |
| Felix Finance | Finance Admin | Finance | FR | — |

---

## 3. Scripted Demo Questions

> These are wired into the UI as clickable example prompts, filtered by the
> logged-in role (`EXAMPLE_PROMPTS` in `frontend/app/page.tsx`). Each carries a
> one-line hint saying what it demonstrates, so a reviewer can walk the whole
> demo without typing or reading this file first. Switching roles swaps the
> list; "Reset" brings it back after a question.

Each entry: who asks, what they ask, what should happen, and *why* it's a good demo moment.

### Scenario A — The headline example (multi-document + versioning)
**As Anna Employee:** "Can I work remotely from Turkey for 30 days?"

Expected: system finds both remote-work docs, resolves that 2026 (20 days) supersedes 2025 (30 days), pulls in the Tax Policy since Turkey is outside the EU, and answers something like:
> "The current policy (2026) allows up to 20 days of remote work abroad, not 30 — this replaced the 2025 policy which allowed 30 days. Since Turkey is outside the EU, you'd also need HR approval regardless of duration under the International Tax Policy. [Sources: Remote Work Policy Germany 2026, International Tax Policy]"

Demonstrates: version resolution + multi-document retrieval + does **not** mention the 40-day HR exception (proves permission filtering, not just prompting).

### Scenario B — Same question, HR user (permission contrast)
**As Helena HR:** "Can I work remotely from Turkey for 30 days?"

Expected: same base answer as Scenario A, **plus** a mention that HR can approve exceptions up to 40 days, citing the HR Internal Guideline.

Demonstrates: the *exact same question* produces a materially different, correctly-scoped answer depending on who asks — the single most convincing live proof that retrieval is permission-aware, not just UI-level role display.

### Scenario C — Direct denial (no workaround, no leak)
**As Anna Employee:** "What is the HR exception policy for remote work days?"

Expected: system does not retrieve Doc 4 at all (filtered at the query layer), and either finds nothing relevant among documents she's allowed to see, or answers only from what's actually available to her, without acknowledging that an HR-only exception document exists.

Demonstrates: asking *directly* for restricted content doesn't leak it via a differently-phrased query — proves the filter is structural, not keyword-matching on the obvious phrasing.

### Scenario D — Pure version question (no multi-doc needed)
**As Mark Manager:** "How many days can I work abroad this year?"

Expected: answers 20 days (2026, current), and — if asked as a natural follow-up — can explain "this used to be 30 days under the 2025 policy."

Demonstrates: version resolution in isolation, and the ability to answer historical follow-ups without it becoming the default answer.

### Scenario E — Clean single-document answer (no conflict, baseline case)
**As Felix Finance:** "What class of flight am I entitled to for a long-haul business trip?"

Expected: straightforward answer from the General Travel Policy, one citation, no conflict, no abstention — the "boring, everything working normally" case, useful to show the system isn't *always* hedging.

### Scenario F — Deliberate abstention
**As anyone:** "Can I expense a home office chair?"

Expected: no seed document covers this — system should respond with a clear "I couldn't find a policy covering this" instead of guessing, and should not cite an unrelated document as if it were relevant.

Demonstrates: abstention behavior on genuinely missing information — the "avoid hallucinating" requirement, shown rather than claimed.

### Scenario G — Department-only denial (no country/version logic involved)
**As Anna Employee:** "What are the salary bands for senior engineers?"

Expected: flat denial/abstention — no salary content retrieved at all.

Demonstrates: the simplest form of RBAC (pure department gate), as a contrast to the more nuanced country+version logic in Scenario A — shows the permission system handles both a simple case and a complex case with the same mechanism.

---

## 4. Suggested Live Demo Order

Run in this order for a ~5 minute walkthrough: **A → B → C → F**. That sequence tells a complete story: here's a hard multi-document question answered correctly (A), here's the same question proving permissions are real (B), here's proof you can't trick it into leaking by rephrasing (C), here's proof it doesn't bluff when it truly doesn't know (F). D, E, and G are good to have in the golden test set for `pytest`, but are optional for the live walkthrough — they're the "boring, everything works" and "simple case" coverage rather than showcase moments.
