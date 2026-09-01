"""
Simple paragraph-aware chunker. At the size of the seed documents (a few
short paragraphs each) most documents end up as one or two chunks -- this
keeps chunk boundaries at natural paragraph breaks rather than mid-sentence,
which matters more for citation quality than raw chunk-size tuning does at
this scale.
"""

MAX_CHUNK_CHARS = 800


def chunk_text(text: str) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if current and len(current) + len(para) + 2 > MAX_CHUNK_CHARS:
            chunks.append(current.strip())
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        chunks.append(current.strip())

    return chunks if chunks else [text.strip()]
