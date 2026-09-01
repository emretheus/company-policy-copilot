import json
import logging

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import User, QueryLog
from app.auth.security import issue_token, get_current_user
from app.retrieval.permissions import allowed_document_ids_subquery
from app.retrieval.search import retrieve
from app.retrieval.geo import geo_facts_for_question
from app.conflict.detector import detect_version_conflict
from app.generation.answer import generate_answer
from app.verification.groundedness import verify_groundedness
from app.schemas import (
    LoginRequest,
    LoginResponse,
    DemoUser,
    AskRequest,
    AskResponse,
    CitationOut,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("policy_copilot")

app = FastAPI(title="Enterprise Policy Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/demo/users", response_model=list[DemoUser])
def list_demo_users(db: Session = Depends(get_db)):
    """Powers the frontend's role-switcher -- lists seeded demo users."""
    users = db.query(User).all()
    return [
        DemoUser(id=u.id, name=u.name, role=u.role, department=u.department, country=u.country)
        for u in users
    ]


@app.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """
    Mock SSO: in production this exchanges a real IdP token for our own
    session token, after validating identity against the company directory.
    Here we skip the IdP and issue a token directly for a seeded demo user id.
    """
    user = db.get(User, req.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Unknown demo user id")
    token = issue_token(user.id)
    return LoginResponse(
        access_token=token,
        user_name=user.name,
        role=user.role,
        department=user.department,
        country=user.country,
    )


@app.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    allowed_doc_ids = allowed_document_ids_subquery(db, user)
    chunks = retrieve(db, req.question, user)

    conflict = detect_version_conflict(chunks)

    if not chunks:
        query_log = QueryLog(
            user_id=user.id,
            question=req.question,
            filter_applied_json={"allowed_document_ids": allowed_doc_ids},
            retrieved_chunk_ids=[],
            answer=None,
            abstained=True,
            verifier_result_json=None,
        )
        db.add(query_log)
        db.commit()
        return AskResponse(
            answer="I couldn't find any policy documents relevant to this question. "
            "I don't want to guess -- please check with HR or the relevant department.",
            abstained=True,
            citations=[],
            has_version_conflict=False,
            trace_id=query_log.id,
        )

    geo_facts = geo_facts_for_question(req.question)
    draft = generate_answer(req.question, chunks, conflict)
    verification = verify_groundedness(draft.text, chunks, verified_facts=geo_facts)

    abstained = not verification.grounded
    final_answer = (
        draft.text
        if verification.grounded
        else "I found some related policy content, but couldn't fully verify the answer "
        "against the source text, so I don't want to risk giving you an incorrect answer. "
        "Please check with HR or the relevant department, or rephrase your question."
    )

    citations = (
        [
            CitationOut(document_title=c.document_title, is_current_version=c.is_current_version, text=c.text)
            for c in chunks
        ]
        if not abstained
        else []
    )

    query_log = QueryLog(
        user_id=user.id,
        question=req.question,
        filter_applied_json={"allowed_document_ids": allowed_doc_ids},
        retrieved_chunk_ids=[c.chunk_id for c in chunks],
        answer=final_answer,
        abstained=abstained,
        verifier_result_json={"grounded": verification.grounded, "reason": verification.reason},
    )
    db.add(query_log)
    db.commit()

    logger.info(
        json.dumps(
            {
                "trace_id": query_log.id,
                "user_id": user.id,
                "role": user.role,
                "department": user.department,
                "question": req.question,
                "retrieved_doc_titles": [c.document_title for c in chunks],
                "grounded": verification.grounded,
                "abstained": abstained,
            }
        )
    )

    return AskResponse(
        answer=final_answer,
        abstained=abstained,
        citations=citations,
        has_version_conflict=conflict.has_version_conflict,
        trace_id=query_log.id,
    )
