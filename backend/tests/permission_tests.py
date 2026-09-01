"""
First-class security test suite: for every seeded role/department
combination, assert restricted documents never appear in the allowed set
or in retrieval results. This suite should block deployment on failure --
see PLAN.md Section 10 ("Permission tests specifically") and Section 11
("Permission-filter integrity check").
"""
from app.models.models import Document
from app.retrieval.permissions import allowed_document_ids_subquery
from app.retrieval.search import retrieve


def _doc_id_by_title(db, title_substring: str) -> str:
    doc = db.query(Document).filter(Document.title.ilike(f"%{title_substring}%")).first()
    assert doc is not None, f"seed data missing expected document containing '{title_substring}'"
    return doc.id


def test_employee_cannot_see_hr_exception_doc(db, anna_employee):
    allowed = allowed_document_ids_subquery(db, anna_employee)
    hr_doc_id = _doc_id_by_title(db, "HR Internal Guideline")
    assert hr_doc_id not in allowed


def test_employee_cannot_see_salary_bands(db, anna_employee):
    allowed = allowed_document_ids_subquery(db, anna_employee)
    salary_doc_id = _doc_id_by_title(db, "Salary Bands")
    assert salary_doc_id not in allowed


def test_manager_cannot_see_hr_exception_doc(db, mark_manager):
    allowed = allowed_document_ids_subquery(db, mark_manager)
    hr_doc_id = _doc_id_by_title(db, "HR Internal Guideline")
    assert hr_doc_id not in allowed


def test_hr_user_can_see_hr_exception_doc(db, helena_hr):
    allowed = allowed_document_ids_subquery(db, helena_hr)
    hr_doc_id = _doc_id_by_title(db, "HR Internal Guideline")
    assert hr_doc_id in allowed


def test_hr_user_can_see_salary_bands(db, helena_hr):
    allowed = allowed_document_ids_subquery(db, helena_hr)
    salary_doc_id = _doc_id_by_title(db, "Salary Bands")
    assert salary_doc_id in allowed


def test_finance_user_cannot_see_hr_only_docs(db, felix_finance):
    allowed = allowed_document_ids_subquery(db, felix_finance)
    hr_doc_id = _doc_id_by_title(db, "HR Internal Guideline")
    salary_doc_id = _doc_id_by_title(db, "Salary Bands")
    assert hr_doc_id not in allowed
    assert salary_doc_id not in allowed


def test_everyone_can_see_general_travel_policy(db, anna_employee, mark_manager, helena_hr, felix_finance):
    travel_doc_id = _doc_id_by_title(db, "General Travel Policy")
    for user in (anna_employee, mark_manager, helena_hr, felix_finance):
        allowed = allowed_document_ids_subquery(db, user)
        assert travel_doc_id in allowed


def test_retrieval_never_surfaces_hr_only_chunk_for_employee(db, anna_employee):
    """
    Even a query worded to directly target the restricted content must not
    surface it -- proves the filter operates at the query layer, not by
    coincidentally not matching keywords. See DEMO_SCENARIOS.md Scenario C.
    """
    results = retrieve(db, "What is the HR exception policy for remote work days, up to 40 days?", anna_employee)
    titles = [c.document_title for c in results]
    assert not any("HR Internal Guideline" in t for t in titles)


def test_retrieval_never_surfaces_salary_chunk_for_employee(db, anna_employee):
    results = retrieve(db, "What are the salary bands for senior engineers?", anna_employee)
    titles = [c.document_title for c in results]
    assert not any("Salary Bands" in t for t in titles)
