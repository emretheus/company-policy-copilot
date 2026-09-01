"""
Document graph queries: version resolution via `supersedes`, and
multi-document assembly via `relates_to` edges. See PLAN.md Section 6 for
why this exists as a small explicit graph rather than being left to
similarity search.
"""
from sqlalchemy.orm import Session

from app.models.models import Document, DocumentRelation


def is_current_version(db: Session, document: Document) -> bool:
    """A document is 'current' if no other document supersedes it."""
    superseded_by = db.query(Document).filter(Document.supersedes_id == document.id).first()
    return superseded_by is None


def get_previous_version(db: Session, document: Document) -> Document | None:
    if document.supersedes_id:
        return db.get(Document, document.supersedes_id)
    return None


def get_related_documents(db: Session, document_id: str) -> list[Document]:
    """Documents connected via `relates_to` / `localizes` edges, in either direction."""
    edges = (
        db.query(DocumentRelation)
        .filter(
            (DocumentRelation.from_document_id == document_id)
            | (DocumentRelation.to_document_id == document_id)
        )
        .all()
    )
    related_ids = set()
    for e in edges:
        other_id = e.to_document_id if e.from_document_id == document_id else e.from_document_id
        related_ids.add(other_id)
    if not related_ids:
        return []
    return db.query(Document).filter(Document.id.in_(related_ids)).all()
