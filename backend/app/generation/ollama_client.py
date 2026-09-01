"""
Thin direct client for Ollama's HTTP API. No LangChain / LlamaIndex --
prompt construction, the request, and response parsing are all explicit
here so the whole generation path is inspectable end to end.
"""
import httpx

from app.config import settings


def embed(text: str) -> list[float]:
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
