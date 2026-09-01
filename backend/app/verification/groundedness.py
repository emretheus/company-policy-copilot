"""
Groundedness / faithfulness check: the backstop against hallucination, per
PLAN.md Section 9. Rather than trusting the generator's own claim that it
only used the provided text, we check the draft independently.

Two layers, deliberately in this order:

  1. A DETERMINISTIC numeric check. Policy answers turn on numbers ("20
     days", "14 days", "6 hours"), and an invented or mis-copied number is
     both the most likely hallucination and the most damaging one. Every
     number in the draft must appear in the sources or the verified facts.
     No model judgement involved, so it cannot be talked out of a rejection.

  2. An LLM CONTRADICTION check, deliberately narrow. Early testing showed
     that asking a small model the open-ended question "is every claim
     supported?" produces unreliable verdicts -- it rejected correct answers
     with confused reasoning, causing false abstentions. Asking the much
     narrower question "does this draft state anything that CONTRADICTS the
     sources?" is a far easier judgement and behaves much more consistently.

The asymmetry is intentional: layer 1 is strict because a wrong number is
unambiguously bad, while layer 2 is lenient because over-refusing is its own
failure mode -- a system that abstains on correct answers gets ignored.

At the model size used here (3B, running locally) layer 2 proved unreliable
even in its narrowed form, so it is currently ADVISORY: its verdict is
recorded for observability but does not block the answer. Layer 1 remains a
hard gate. See CONTRADICTION_CHECK_BLOCKS below -- with a stronger verifier
model this should be turned back into a gate and re-validated against the
golden set.
"""
import re
from dataclasses import dataclass

from app.retrieval.search import RetrievedChunk
from app.generation.ollama_client import generate

CONTRADICTION_SYSTEM_PROMPT = """You check whether a draft answer contradicts
its sources.

You will be given source excerpts, verified facts, and a draft answer.
Answer ONE question: does the draft state anything that DIRECTLY CONTRADICTS
the excerpts or the verified facts?

Important:
- The verified facts are established ground truth. Relying on them is fine.
- Being cautious, recommending the user confirm with HR, or noting that a
  policy was superseded is NOT a contradiction.
- Omitting information is NOT a contradiction.
- Only say yes if the draft asserts something the sources say is false.

Respond in exactly this format, nothing else:
CONTRADICTS: no
or
CONTRADICTS: yes
REASON: <the contradicting claim>
"""


# Whether a failed LLM contradiction check blocks the answer. False while
# running a small local model (too many false positives); set True when
# using a verifier model strong enough to be trusted as a gate.
CONTRADICTION_CHECK_BLOCKS = False


@dataclass
class VerificationResult:
    grounded: bool
    reason: str | None


def _extract_numbers(text: str) -> set[str]:
    """Bare integers, ignoring those inside years/dates and citation markers."""
    cleaned = re.sub(r"\b(19|20)\d{2}\b", " ", text)  # drop years
    return set(re.findall(r"\b\d{1,4}\b", cleaned))


def check_numbers_grounded(
    draft_answer: str, chunks: list[RetrievedChunk], verified_facts: list[str] | None
) -> tuple[bool, str | None]:
    source_text = " ".join(c.text for c in chunks)
    if verified_facts:
        source_text += " " + " ".join(verified_facts)
    source_numbers = _extract_numbers(source_text)

    for number in _extract_numbers(draft_answer):
        if number not in source_numbers:
            return False, f"The figure '{number}' does not appear in any source document."
    return True, None


def check_no_contradiction(
    draft_answer: str, chunks: list[RetrievedChunk], verified_facts: list[str] | None
) -> tuple[bool, str | None]:
    context = "\n\n".join(f'"{c.document_title}": {c.text}' for c in chunks)
    facts_block = ""
    if verified_facts:
        facts_block = "Verified facts:\n" + "\n".join(f"- {f}" for f in verified_facts) + "\n\n"

    prompt = f"{facts_block}Source excerpts:\n{context}\n\nDraft answer:\n{draft_answer}\n\nVerdict:"
    response = generate(prompt, system=CONTRADICTION_SYSTEM_PROMPT).strip().lower()

    if "contradicts: yes" in response:
        return False, response
    return True, None


def verify_groundedness(
    draft_answer: str,
    chunks: list[RetrievedChunk],
    verified_facts: list[str] | None = None,
) -> VerificationResult:
    if not chunks:
        return VerificationResult(grounded=False, reason="No source excerpts were provided.")

    numbers_ok, numbers_reason = check_numbers_grounded(draft_answer, chunks, verified_facts)
    if not numbers_ok:
        return VerificationResult(grounded=False, reason=numbers_reason)

    # The LLM contradiction check is ADVISORY at this model size, not a gate.
    # A 3B model produces false positives here often enough that gating on it
    # abstains on correct answers -- during testing it flagged a contradiction
    # while its own stated reasoning agreed with the draft. We record the
    # verdict for observability (PLAN.md Section 11 tracks verifier-rejection
    # rate as a quality signal) but do not block the answer on it.
    #
    # With a stronger verifier model this should become a hard gate again:
    # flip `CONTRADICTION_CHECK_BLOCKS` to True and re-run the golden set.
    no_contradiction, contradiction_reason = check_no_contradiction(
        draft_answer, chunks, verified_facts
    )
    if CONTRADICTION_CHECK_BLOCKS and not no_contradiction:
        return VerificationResult(grounded=False, reason=contradiction_reason)

    return VerificationResult(
        grounded=True,
        reason=None if no_contradiction else f"advisory (non-blocking): {contradiction_reason}",
    )
