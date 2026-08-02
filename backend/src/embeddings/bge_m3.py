"""BGE-M3 embedding provider — the real model (LEG-58).

Wraps BAAI/bge-m3, a multilingual, retrieval-tuned model with strong Arabic
support, chosen to match the 1024-wide pgvector column (see
foundation.models.EMBEDDING_DIMENSIONS).

Loading the actual model needs `sentence-transformers` installed — a heavy,
optional dependency (`uv sync --extra embeddings`), deliberately kept out of
the default/dev install so CI and everyday development stay fast. This
module has no import-time dependency on that package: the import only
happens inside _load_default_model, so tests can exercise everything this
wrapper does (batching, order, normalisation, dimension checks) by injecting
a fake encoder, without sentence-transformers ever being installed.
"""

from typing import Protocol, cast

from embeddings.base import EmbeddingProvider, Vector

MODEL_NAME = "BAAI/bge-m3"
DIMENSIONS = 1024


class _Encoder(Protocol):
    """The one capability this provider needs from a loaded model."""

    def encode(self, texts: list[str]) -> list[list[float]]: ...


def _load_default_model() -> _Encoder:
    """Downloads (on first use) and loads the real BGE-M3 weights."""
    from sentence_transformers import SentenceTransformer

    # sentence-transformers ships no type stubs, so SentenceTransformer(...)
    # is Any as far as mypy can tell — cast rather than let that Any leak
    # into every caller of this function.
    return cast(_Encoder, SentenceTransformer(MODEL_NAME))


class BgeM3EmbeddingProvider(EmbeddingProvider):
    """Real embeddings via BGE-M3, run locally — no API key, no network call
    at inference time once the weights are cached.

    Accepts an injected encoder for testing; production code should
    construct it with no arguments so the real model loads.
    """

    def __init__(self, model: _Encoder | None = None) -> None:
        self._model = model if model is not None else _load_default_model()

    @property
    def dimensions(self) -> int:
        return DIMENSIONS

    def embed(self, texts: list[str]) -> list[Vector]:
        if not texts:
            return []

        raw_vectors = self._model.encode(texts)
        return [self._normalise(vector) for vector in raw_vectors]

    def _normalise(self, vector: list[float]) -> Vector:
        if len(vector) != self.dimensions:
            raise ValueError(
                f"Model produced a {len(vector)}-wide vector, expected {self.dimensions}"
            )
        length = sum(value * value for value in vector) ** 0.5
        if length == 0.0:
            return [1.0] + [0.0] * (self.dimensions - 1)
        return [value / length for value in vector]
