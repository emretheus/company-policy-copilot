"""
Golden question set from DEMO_SCENARIOS.md, run end to end (retrieval ->
generation -> verification). Requires Ollama running with the configured
models pulled -- these are slower, LLM-dependent tests, kept separate from
the fast deterministic retrieval_tests.py suite.
"""
from app.retrieval.search import retrieve
from app.retrieval.geo import geo_facts_for_question
from app.conflict.detector import detect_version_conflict
from app.generation.answer import generate_answer
from app.verification.groundedness import verify_groundedness


def _ask(db, user, question):
    chunks = retrieve(db, question, user)
    conflict = detect_version_conflict(chunks)
    draft = generate_answer(question, chunks, conflict)
    verification = verify_groundedness(draft.text, chunks, verified_facts=geo_facts_for_question(question))
    return chunks, draft, verification


def test_scenario_a_turkey_multi_doc_versioning(db, anna_employee):
    chunks, draft, verification = _ask(db, anna_employee, "Can I work remotely from Turkey for 30 days?")
    assert verification.grounded
    assert "20" in draft.text
    assert not any("HR Internal Guideline" in c.document_title for c in chunks)


def test_scenario_b_hr_user_sees_exception_mentioned(db, helena_hr):
    chunks, draft, verification = _ask(db, helena_hr, "Can I work remotely from Turkey for 30 days?")
    assert verification.grounded
    assert any("HR Internal Guideline" in c.document_title for c in chunks)


def test_scenario_f_abstains_on_unanswerable_question(db, anna_employee):
    chunks, draft, verification = _ask(db, anna_employee, "Can I expense a home office chair?")
    assert len(chunks) == 0 or not verification.grounded
