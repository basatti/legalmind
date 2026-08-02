"""Company-hosted BGE-M3 embeddings, via an OpenAI-compatible API (LEG-58).

Same model as BgeM3EmbeddingProvider (BAAI/bge-m3, 1024-dim, already
normalised) — this just calls it over the network instead of loading the
weights on this machine. Chunks already embedded with the local provider and
chunks embedded through this one are comparable, because it's the same model
either way.

Config comes from the environment so switching endpoints or keys is a config
change, not a code change — mirrors OllamaLLMProvider.
"""

import os
from typing import Any

import httpx

from embeddings.base import EmbeddingProvider, Vector

DEFAULT_MODEL = "bge-m3"
DEFAULT_DIMENSIONS = 1024
DEFAULT_TIMEOUT_SECONDS = 60.0


class EmbeddingError(RuntimeError):
    """The remote embedding service could not be reached or returned nonsense."""


class CompanyEmbeddingProvider(EmbeddingProvider):
    """Talks to the company's hosted embedding endpoint.

    Accepts an injected transport so the request this builds can be inspected
    without a live server — the same reason OllamaLLMProvider does.
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int = DEFAULT_DIMENSIONS,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_url = (api_url or os.environ["COMPANY_API_URL"]).rstrip("/")
        self.api_key = api_key or os.environ["COMPANY_API_KEY"]
        self.model = model or os.environ.get("COMPANY_EMBEDDING_MODEL", DEFAULT_MODEL)
        self._dimensions = dimensions
        self.timeout = timeout
        self._transport = transport

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: list[str]) -> list[Vector]:
        if not texts:
            return []

        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(
                    f"{self.api_url}/v1/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "input": texts},
                )
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Could not reach {self.api_url}: {exc}") from exc

        if response.status_code != 200:
            raise EmbeddingError(
                f"Embedding API returned {response.status_code}: {response.text[:300]}"
            )

        return self._vectors(response.json(), expected=len(texts))

    def _vectors(self, payload: Any, expected: int) -> list[Vector]:
        try:
            rows = sorted(payload["data"], key=lambda row: row["index"])
            vectors = [row["embedding"] for row in rows]
        except (KeyError, TypeError) as exc:
            raise EmbeddingError(f"Unexpected response shape: {payload}") from exc

        if len(vectors) != expected:
            raise EmbeddingError(f"Expected {expected} vectors, got {len(vectors)}")
        for vector in vectors:
            if len(vector) != self._dimensions:
                raise EmbeddingError(
                    f"Model produced a {len(vector)}-wide vector, expected {self._dimensions}"
                )
        return vectors
