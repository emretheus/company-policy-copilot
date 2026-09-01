"""
Permission context builder.

Turns a logged-in user into a concrete SQL-evaluable predicate over
`document_access_rules`, and applies it as a hard filter at query time --
not as a post-hoc check on already-retrieved text. This is the security
boundary described in PLAN.md Section 4: unauthorized chunks are never
retrieved, never scored, never sent to the LLM.

Each document has one or more access rules (JSON). A document is visible
to a user if ANY of its rules evaluates to true for that user. Supported
rule shapes (kept intentionally small -- see PLAN.md Section 4):

  {"scope": "all"}
  {"scope": "department", "department": "HR"}
  {"scope": "department_or_role", "department": "Finance", "role": "Manager"}
  {"scope": "owner_manager_hr", "owner_id": "<user-id>"}   -- performance docs
"""
from app.models.models import User, DocumentAccessRule


def rule_matches(rule: dict, user: User) -> bool:
    scope = rule.get("scope")

    if scope == "all":
        return True

    if scope == "department":
        return user.department == rule.get("department")

    if scope == "department_or_role":
        return user.department == rule.get("department") or user.role == rule.get("role")

    if scope == "owner_manager_hr":
        # The "manager of the owner" case needs a DB lookup (the owner's
        # manager_id) that this function doesn't have access to -- it's
        # resolved separately in `allowed_document_ids_subquery` below.
        # Here we can only check the two cases answerable from the rule
        # + requesting user alone.
        owner_id = rule.get("owner_id")
        is_owner = user.id == owner_id
        is_hr = user.department == "HR"
        return is_owner or is_hr

    return False


def any_rule_grants_access(rules: list[DocumentAccessRule], user: User) -> bool:
    """True if ANY rule attached to the document grants this user access."""
    return any(rule_matches(r.rule_json, user) for r in rules)


def allowed_document_ids_subquery(db_session, user: User) -> list[str]:
    """
    Evaluate access rules in Python against every document's rules and
    return the list of document ids this user may see. At this project's
    scale (tens of thousands of documents, a handful of rule shapes) this
    is simpler and more auditable than compiling rules into raw SQL, and
    it runs once per query, not once per chunk.
    """
    from app.models.models import Document

    documents = db_session.query(Document).all()
    allowed = []
    for doc in documents:
        if any_rule_grants_access(doc.access_rules, user):
            allowed.append(doc.id)
        else:
            # owner_manager_hr needs the manager chain, which requires a
            # DB lookup the pure `rule_matches` function doesn't have.
            for rule in doc.access_rules:
                if rule.rule_json.get("scope") == "owner_manager_hr":
                    owner_id = rule.rule_json.get("owner_id")
                    owner = db_session.get(User, owner_id) if owner_id else None
                    if owner is not None and owner.manager_id == user.id:
                        allowed.append(doc.id)
                        break
    return allowed
