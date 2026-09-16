"""Embedding providers.

Memo is meant to be runnable by anyone who clones it, so there are three tiers
and it picks the best one available without being told:

    openai  - an API key is set. Best quality.
    ollama  - Ollama is running locally. Free, private, offline.
    none    - neither. Search falls back to SQLite FTS5 (lexical), which still works.

Vectors from different models are not comparable even at equal dimensions, so
each provider carries a fingerprint the database checks before trusting a store.
"""

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import httpx

log = logging.getLogger(__name__)

# 768 matches nomic-embed-text natively and is a clean truncation target for
# text-embedding-3-small. Half the storage of 1536 with no practical loss at
# personal-library scale.
DEFAULT_DIM = int(os.getenv("MEMO_EMBED_DIM", "768"))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OPENAI_MODEL = os.getenv("MEMO_OPENAI_EMBED_MODEL", "text-embedding-3-small")
OLLAMA_MODEL = os.getenv("MEMO_OLLAMA_EMBED_MODEL", "nomic-embed-text")


@dataclass
class ProviderStatus:
    name: str          # openai | ollama | none
    model: str
    dim: int
    ok: bool
    detail: str = ""

    @property
    def fingerprint(self) -> str:
        return f"{self.name}:{self.model}:{self.dim}"


class EmbeddingProvider:
    """Base: the null provider. Embeds nothing; lexical search covers for it."""

    name = "none"

    def __init__(self, dim: int = DEFAULT_DIM):
        self.dim = dim
        self.model = "-"

    def embed(self, text: str) -> Optional[List[float]]:
        return None

    def probe(self) -> ProviderStatus:
        return ProviderStatus(
            self.name, self.model, self.dim, ok=False,
            detail="No embedding provider — search uses keyword matching. "
                   "Set OPENAI_API_KEY, or run Ollama, for semantic search.",
        )

    @property
    def status(self) -> ProviderStatus:
        if not hasattr(self, "_status"):
            self._status = self.probe()
        return self._status


class OpenAIEmbeddings(EmbeddingProvider):
    name = "openai"

    def __init__(self, api_key: str, dim: int = DEFAULT_DIM):
        super().__init__(dim)
        self.model = OPENAI_MODEL
        import openai

        self._client = openai.OpenAI(api_key=api_key)

    def embed(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        try:
            resp = self._client.embeddings.create(
                input=text[:8000], model=self.model, dimensions=self.dim
            )
            return resp.data[0].embedding
        except Exception as exc:
            log.warning("openai embedding failed: %s", exc)
            return None

    def probe(self) -> ProviderStatus:
        """One tiny call, so a bad key is reported at startup rather than
        silently degrading every later search to zero results."""
        try:
            resp = self._client.embeddings.create(
                input="ping", model=self.model, dimensions=self.dim
            )
            got = len(resp.data[0].embedding)
            if got != self.dim:
                return ProviderStatus(self.name, self.model, self.dim, False,
                                      f"expected {self.dim} dims, provider returned {got}")
            return ProviderStatus(self.name, self.model, self.dim, True)
        except Exception as exc:
            return ProviderStatus(self.name, self.model, self.dim, False, str(exc)[:200])


class OllamaEmbeddings(EmbeddingProvider):
    name = "ollama"

    def __init__(self, host: str = OLLAMA_HOST, dim: int = DEFAULT_DIM):
        super().__init__(dim)
        self.host = host
        self.model = OLLAMA_MODEL

    def embed(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        try:
            r = httpx.post(
                f"{self.host}/api/embed",
                json={"model": self.model, "input": text[:8000]},
                timeout=30.0,
            )
            r.raise_for_status()
            vec = r.json()["embeddings"][0]
            return vec if len(vec) == self.dim else None
        except Exception as exc:
            log.warning("ollama embedding failed: %s", exc)
            return None

    def probe(self) -> ProviderStatus:
        try:
            tags = httpx.get(f"{self.host}/api/tags", timeout=3.0)
            tags.raise_for_status()
            installed = {m["name"].split(":")[0] for m in tags.json().get("models", [])}
            if self.model.split(":")[0] not in installed:
                return ProviderStatus(
                    self.name, self.model, self.dim, False,
                    f"Ollama is running but '{self.model}' is not pulled. "
                    f"Run: ollama pull {self.model}",
                )
            vec = self.embed("ping")
            if vec is None:
                return ProviderStatus(self.name, self.model, self.dim, False,
                                      f"'{self.model}' did not return {self.dim}-dim vectors")
            return ProviderStatus(self.name, self.model, self.dim, True)
        except Exception as exc:
            return ProviderStatus(self.name, self.model, self.dim, False,
                                  f"Ollama not reachable at {self.host}: {str(exc)[:120]}")


def resolve_provider(dim: int = DEFAULT_DIM) -> EmbeddingProvider:
    """Pick the best provider available. MEMO_EMBED_PROVIDER forces one."""
    choice = os.getenv("MEMO_EMBED_PROVIDER", "auto").lower()
    key = os.getenv("OPENAI_API_KEY", "").strip()

    if choice == "openai" or (choice == "auto" and key):
        if not key:
            log.warning("MEMO_EMBED_PROVIDER=openai but OPENAI_API_KEY is unset")
        else:
            provider = OpenAIEmbeddings(key, dim)
            if choice == "openai" or provider.status.ok:
                return provider
            log.warning("OpenAI unusable (%s) — trying Ollama", provider.status.detail)

    if choice in ("ollama", "auto"):
        provider = OllamaEmbeddings(dim=dim)
        if choice == "ollama" or provider.status.ok:
            return provider

    return EmbeddingProvider(dim)
