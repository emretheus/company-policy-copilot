"""
Conflict detection over a retrieved chunk set. Two categories, per
PLAN.md Section 8:

  1. Version conflicts: multiple chunks from the same document family --
     resolved deterministically (the non-superseded one is "current"),
     the older one kept only as context ("this changed from X to Y").
  2. Genuine contradictions: not modeled by the graph at all in this MVP
     (no two unrelated seed documents actually disagree) -- flagged only
     as "multiple sources found", per PLAN.md Section 14's MVP scope.
"""
from dataclasses import dataclass

from app.retrieval.search import RetrievedChunk


@dataclass
class ConflictInfo:
    has_version_conflict: bool
    current_chunk_ids: list[str]
    superseded_chunk_ids: list[str]


def detect_version_conflict(chunks: list[RetrievedChunk]) -> ConflictInfo:
    current_ids = [c.chunk_id for c in chunks if c.is_current_version]
    superseded_ids = [c.chunk_id for c in chunks if not c.is_current_version]

    # A version conflict only matters if both an old and current chunk from
    # the SAME underlying topic were retrieved together (title match is a
    # simple proxy for "same family" at this scale -- the family_id would
    # be more precise but title is enough given the seed data).
    titles_current = {c.document_title.rsplit(" ", 1)[0] for c in chunks if c.is_current_version}
    titles_superseded = {c.document_title.rsplit(" ", 1)[0] for c in chunks if not c.is_current_version}
    has_conflict = bool(titles_current & titles_superseded)

    return ConflictInfo(
        has_version_conflict=has_conflict,
        current_chunk_ids=current_ids,
        superseded_chunk_ids=superseded_ids,
    )
