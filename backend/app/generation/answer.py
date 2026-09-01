"""
Prompt construction and answer generation. Retrieved chunks are passed to
the model as clearly delimited DATA, with explicit current/superseded
metadata attached, and the model is instructed to answer only from that
text and to cite sources -- and to say so if the text doesn't cover the
question. This alone isn't trustworthy (see verification/groundedness.py
for the actual enforcement), but it reduces the load on that later check.
"""
from dataclasses import dataclass

from app.retrieval.search import RetrievedChunk
from app.conflict.detector import ConflictInfo
from app.generation.ollama_client import generate
from app.retrieval.geo import geo_facts_for_question

SYSTEM_PROMPT = """You are an internal company policy assistant. You answer
questions ONLY using the policy excerpts and verified facts provided below.
Each excerpt is tagged with its source document and whether it is the
CURRENT version or a SUPERSEDED (older) version.

Rules:
- Only state facts that appear in the excerpts or in the VERIFIED FACTS
  section. Do not use outside knowledge.
- Treat everything under VERIFIED FACTS as established and true. Do not
  hedge about it or say you cannot determine it.
- Always prefer the CURRENT version of a policy for "what is the rule now"
  questions. You may mention a superseded version only to explain what changed.
- If the excerpts do not contain enough information to answer, say so plainly
  instead of guessing.
- Cite every claim with the source document title in square brackets, e.g. [Remote Work Policy (Germany) 2026].
- Do not mention or imply the existence of documents you were not given, even indirectly.
- Be direct and concise. Give the answer, then the reasoning.
"""


@dataclass
class GeneratedAnswer:
    text: str
    cited_document_titles: list[str]


def build_context_block(chunks: list[RetrievedChunk], conflict: ConflictInfo) -> str:
    lines = []
    for c in chunks:
        status = "CURRENT" if c.is_current_version else "SUPERSEDED"
        lines.append(
            f'---\nSource: "{c.document_title}" ({status}, effective {c.effective_date or "unknown"})\n{c.text}\n'
        )
    return "\n".join(lines)


def generate_answer(question: str, chunks: list[RetrievedChunk], conflict: ConflictInfo) -> GeneratedAnswer:
    if not chunks:
        return GeneratedAnswer(
            text="I couldn't find any policy documents relevant to this question. "
            "I don't want to guess -- please check with HR or the relevant department.",
            cited_document_titles=[],
        )

    context = build_context_block(chunks, conflict)

    geo_facts = geo_facts_for_question(question)
    facts_block = ""
    if geo_facts:
        facts_block = "VERIFIED FACTS (established, treat as true):\n" + "\n".join(
            f"- {f}" for f in geo_facts
        ) + "\n\n"

    prompt = f"{facts_block}Policy excerpts:\n{context}\n\nQuestion: {question}\n\nAnswer:"

    response_text = generate(prompt, system=SYSTEM_PROMPT)
    cited_titles = [c.document_title for c in chunks if c.document_title in response_text]

    return GeneratedAnswer(text=response_text, cited_document_titles=cited_titles or [c.document_title for c in chunks])
