"""
Loads seed_data/metadata.yaml + the referenced document text files into the
database: users, documents (with family/supersedes), access rules, relation
edges, and chunk+embed each document's content.

Run with: python -m app.ingestion.seed
"""
import hashlib
import os
from datetime import datetime

import yaml

from app.db.session import SessionLocal
from app.models.models import (
    User,
    DocumentFamily,
    Document,
    DocumentAccessRule,
    DocumentRelation,
    Chunk,
)
from app.ingestion.chunking import chunk_text
from app.generation.ollama_client import embed

# Mounted at /seed_data by docker-compose; overridable so the same script
# runs outside the container (e.g. in CI, from a repo checkout).
SEED_DIR = os.environ.get("SEED_DATA_DIR", "/seed_data")


def load_metadata():
    with open(f"{SEED_DIR}/metadata.yaml") as f:
        return yaml.safe_load(f)


def seed():
    meta = load_metadata()
    db = SessionLocal()

    try:
        # --- users ---
        key_to_user_id: dict[str, str] = {}
        for u in meta["users"]:
            existing = db.query(User).filter_by(email=u["email"]).first()
            if existing:
                key_to_user_id[u["key"]] = existing.id
                continue
            user = User(
                name=u["name"],
                email=u["email"],
                role=u["role"],
                department=u["department"],
                country=u["country"],
                manager_id=None,  # resolved in a second pass below
            )
            db.add(user)
            db.flush()
            key_to_user_id[u["key"]] = user.id

        for u in meta["users"]:
            if u.get("manager"):
                user = db.get(User, key_to_user_id[u["key"]])
                user.manager_id = key_to_user_id[u["manager"]]
        db.commit()

        # --- document families ---
        family_key_to_id: dict[str, str] = {}
        for fam in meta.get("document_families", []):
            existing = db.query(DocumentFamily).filter_by(title_base=fam["title_base"]).first()
            if existing:
                family_key_to_id[fam["id"]] = existing.id
                continue
            df = DocumentFamily(title_base=fam["title_base"])
            db.add(df)
            db.flush()
            family_key_to_id[fam["id"]] = df.id
        db.commit()

        # --- documents (two passes: create, then wire supersedes) ---
        key_to_doc_id: dict[str, str] = {}
        for d in meta["documents"]:
            existing = db.query(Document).filter_by(title=d["title"]).first()
            if existing:
                key_to_doc_id[d["key"]] = existing.id
                continue

            with open(f"{SEED_DIR}/documents/{d['file']}") as f:
                content = f.read()
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            doc = Document(
                family_id=family_key_to_id.get(d["family"]) if d.get("family") else None,
                title=d["title"],
                version_label=d.get("version_label"),
                effective_date=datetime.strptime(d["effective_date"], "%Y-%m-%d").date()
                if d.get("effective_date")
                else None,
                supersedes_id=None,  # wired in second pass
                country=d.get("country"),
                source_type="seed",
                source_uri=d["file"],
                content_hash=content_hash,
                ingested_at=datetime.utcnow(),
            )
            db.add(doc)
            db.flush()
            key_to_doc_id[d["key"]] = doc.id

            for rule in d.get("access_rules", []):
                db.add(DocumentAccessRule(document_id=doc.id, rule_json=rule))

            for i, chunk in enumerate(chunk_text(content)):
                db.add(
                    Chunk(
                        document_id=doc.id,
                        text=chunk,
                        embedding=embed(chunk),
                        token_count=len(chunk.split()),
                        chunk_index=i,
                    )
                )
        db.commit()

        for d in meta["documents"]:
            if d.get("supersedes"):
                doc = db.get(Document, key_to_doc_id[d["key"]])
                doc.supersedes_id = key_to_doc_id[d["supersedes"]]
        db.commit()

        # --- relations ---
        for rel in meta.get("document_relations", []):
            from_id = key_to_doc_id[rel["from"]]
            to_id = key_to_doc_id[rel["to"]]
            existing = (
                db.query(DocumentRelation)
                .filter_by(from_document_id=from_id, to_document_id=to_id, relation_type=rel["type"])
                .first()
            )
            if not existing:
                db.add(
                    DocumentRelation(
                        from_document_id=from_id,
                        to_document_id=to_id,
                        relation_type=rel["type"],
                    )
                )
        db.commit()

        print(f"Seeded {len(key_to_user_id)} users, {len(key_to_doc_id)} documents.")
        print("Demo user ids (for login):")
        for key, uid in key_to_user_id.items():
            print(f"  {key}: {uid}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
