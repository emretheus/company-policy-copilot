"""
Retrieval-quality tests: does the right document get retrieved, is version
resolution correct, does graph expansion pull in related documents. These
don't depend on the LLM generation/verification steps, so they're fast and
deterministic -- separate from golden_qa.py, which exercises the full
pipeline including generation.
"""
from app.retrieval.search import retrieve
from app.graph.graph import is_current_version
from app.models.models import Document


def test_current_remote_work_version_is_2026(db, anna_employee):
    results = retrieve(db, "How many days can I work remotely abroad?", anna_employee)
    current = [c for c in results if "Remote Work Policy" in c.document_title and c.is_current_version]
    assert any("2026" in c.document_title for c in current)


def test_superseded_2025_version_is_flagged_not_current(db):
    doc_2025 = db.query(Document).filter(Document.title.ilike("%2025%")).first()
    assert doc_2025 is not None
    assert is_current_version(db, doc_2025) is False


def test_turkey_question_pulls_in_tax_policy(db, anna_employee):
    results = retrieve(db, "Can I work remotely from Turkey for 30 days?", anna_employee)
    titles = [c.document_title for c in results]
    assert any("Remote Work Policy" in t for t in titles)
    assert any("International Tax Policy" in t for t in titles)


def test_travel_question_returns_single_clean_source(db, felix_finance):
    results = retrieve(db, "What class of flight am I entitled to for a long trip?", felix_finance)
    titles = [c.document_title for c in results]
    assert any("General Travel Policy" in t for t in titles)
