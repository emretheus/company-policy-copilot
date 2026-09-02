"""
Thin direct client for Ollama's HTTP API. No LangChain / LlamaIndex --
prompt construction, the request, and response parsing are all explicit
here so the whole generation path is inspectable end to end.
"""
import hashlib
import os
import struct

import httpx

from app.config import settings

# CI runs without an Ollama instance. Stub embeddings are deterministic and
# unit-norm so vector queries execute and permission/version logic can be
# tested end to end -- but they are hash-derived, so semantically related
# text does NOT land near each other. Anything asserting on ranking quality
# or the relevance threshold needs a real embedding model.
USE_STUB_EMBEDDINGS = os.environ.get("USE_STUB_EMBEDDINGS") == "1"


def _stub_embedding(text: str) -> list[float]:
    dim = settings.embedding_dim
    raw = b""
    counter = 0
    while len(raw) < dim * 4:
        raw += hashlib.sha256(f"{text}:{counter}".encode()).digest()
        counter += 1
    values = [struct.unpack("<f", raw[i * 4 : i * 4 + 4])[0] for i in range(dim)]
    values = [v if v == v and abs(v) != float("inf") else 0.0 for v in values]  # drop NaN/inf
    norm = sum(v * v for v in values) ** 0.5
    if norm == 0:
        return [1.0] + [0.0] * (dim - 1)
    return [v / norm for v in values]


def embed(text: str) -> list[float]:
    if USE_STUB_EMBEDDINGS:
        return _stub_embedding(text)
    resp = httpx.post(
        f"{settings.ollama_base_url}/api/embeddings",
        json={"model": settings.ollama_embedding_model, "prompt": text},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def generate(prompt: str, system: str | None = None) -> str:
    payload = {
        "model": settings.ollama_generation_model,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    # Generous timeout: an 8B model on CPU can take minutes per call, and
    # each /ask makes two calls (draft answer, then groundedness check).
    resp = httpx.post(
        f"{settings.ollama_base_url}/api/generate",
        json=payload,
        timeout=600.0,
    )
    resp.raise_for_status()
    return resp.json()["response"]
