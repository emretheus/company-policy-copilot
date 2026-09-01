"""
Permission-filtered hybrid retrieval: vector search + keyword (full-text)
search, both restricted to documents the requesting user is allowed to see,
combined with reciprocal rank fusion. Then expanded via the document graph
to pull in related documents (e.g. Tax Policy alongside Remote Work Policy).

The permission filter is applied as a SQL `document_id IN (...)` clause
BEFORE scoring -- unauthorized chunks are never fetched from the database,
let alone scored or shown to the model. See PLAN.md Section 4-5.
"""
from dataclasses import dataclass
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.models import Chunk, Document, User
from app.retrieval.permissions import allowed_document_ids_subquery
from app.graph.graph import get_related_documents, is_current_version
from app.generation.ollama_client import embed

TOP_K = 5
RRF_K = 60

# Cosine-distance ceiling for a chunk to count as relevant at all. This is
# abstention layer 1 from PLAN.md Section 9: if nothing clears the bar, we
# return nothing and the caller abstains, rather than handing the model
# loosely-related text it will feel obliged to answer from.
#
# Calibrated against the seed corpus with nomic-embed-text:
#   on-topic questions      -> nearest chunk at 0.25-0.36
#   off-topic ("expense a chair", "capital of Brazil") -> 0.48+
# 0.42 sits in the gap. Re-measure if the embedding model changes.
MAX_RELEVANT_DISTANCE = 0.42


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_title: str
    text: str
    is_current_version: bool
    effective_date: str | None


def vector_search(db: Session, query: str, allowed_doc_ids: list[str], top_k: int = TOP_K) -> list[str]:
    if not allowed_doc_ids:
        return []
    query_embedding = embed(query)
    distance = Chunk.embedding.cosine_distance(query_embedding)
    rows = db.execute(
        select(Chunk.id)
        .where(Chunk.document_id.in_(allowed_doc_ids))
        .where(distance <= MAX_RELEVANT_DISTANCE)
        .order_by(distance)
        .limit(top_k)
    ).all()
    return [r[0] for r in rows]


def keyword_search(db: Session, query: str, allowed_doc_ids: list[str], top_k: int = TOP_K) -> list[str]:
    if not allowed_doc_ids:
        return []
    rows = db.execute(
        text(
            """
            SELECT id FROM chunks
            WHERE document_id = ANY(:doc_ids)
              AND text_search @@ plainto_tsquery('english', :query)
            ORDER BY ts_rank(text_search, plainto_tsquery('english', :query)) DESC
            LIMIT :top_k
            """
        ),
        {"doc_ids": allowed_doc_ids, "query": query, "top_k": top_k},
    ).all()
    return [r[0] for r in rows]


def reciprocal_rank_fusion(rank_lists: list[list[str]], k: int = RRF_K) -> list[str]:
    scores: dict[str, float] = {}
    for ranked_ids in rank_lists:
        for rank, chunk_id in enumerate(ranked_ids):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)


def retrieve(db: Session, query: str, user: User, top_k: int = TOP_K) -> list[RetrievedChunk]:
    allowed_doc_ids = allowed_document_ids_subquery(db, user)

    vector_ids = vector_search(db, query, allowed_doc_ids, top_k=top_k)

    # If nothing clears the semantic relevance floor, treat the question as
    # out of scope and retrieve nothing at all. Keyword search is skipped
    # deliberately here: it matches on incidental word overlap (an expenses
    # question hitting "expenses" in the travel policy) and would otherwise
    # smuggle irrelevant text past the floor, which is what makes the model
    # answer questions the corpus does not cover.
    if not vector_ids:
        return []

    keyword_ids = keyword_search(db, query, allowed_doc_ids, top_k=top_k)
    fused_ids = reciprocal_rank_fusion([vector_ids, keyword_ids])[:top_k]

    chunks = db.query(Chunk).filter(Chunk.id.in_(fused_ids)).all()
    chunks_by_id = {c.id: c for c in chunks}
    ordered_chunks = [chunks_by_id[cid] for cid in fused_ids if cid in chunks_by_id]

    # Graph expansion: for each retrieved document, pull in related documents
    # (e.g. Tax Policy alongside Remote Work Policy) if the user can see them
    # and they're not already represented in the result set.
    seen_doc_ids = {c.document_id for c in ordered_chunks}
    expansion_chunks: list[Chunk] = []
    for c in list(ordered_chunks):
        related = get_related_documents(db, c.document_id)
        for rel_doc in related:
            if rel_doc.id in allowed_doc_ids and rel_doc.id not in seen_doc_ids:
                top_chunk = (
                    db.query(Chunk)
                    .filter(Chunk.document_id == rel_doc.id)
                    .order_by(Chunk.chunk_index)
                    .first()
                )
                if top_chunk:
                    expansion_chunks.append(top_chunk)
                    seen_doc_ids.add(rel_doc.id)

    all_chunks = ordered_chunks + expansion_chunks

    results = []
    for c in all_chunks:
        doc = db.get(Document, c.document_id)
        results.append(
            RetrievedChunk(
                chunk_id=c.id,
                document_id=doc.id,
                document_title=doc.title,
                text=c.text,
                is_current_version=is_current_version(db, doc),
                effective_date=doc.effective_date.isoformat() if doc.effective_date else None,
            )
        )
    return results
