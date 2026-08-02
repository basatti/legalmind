"""Defers building an expensive provider until something actually embeds text.

Loading BGE-M3 reads roughly 2GB from disk. Building it while a web request's
dependencies are being resolved makes every request pay that cost — including
requests rejected for authentication, and requests from users authorised for
nothing, which never search at all. This builds the real provider on first use
and keeps it.
"""

from collections.abc import Callable

from embeddings.base import EmbeddingProvider, Vector


class LazyEmbeddingProvider(EmbeddingProvider):
    """An EmbeddingProvider that builds its delegate on first use."""

    def __init__(self, build: Callable[[], EmbeddingProvider]) -> None:
        self._build = build
        self._delegate: EmbeddingProvider | None = None

    @property
    def _loaded(self) -> EmbeddingProvider:
        if self._delegate is None:
            self._delegate = self._build()
        return self._delegate

    @property
    def dimensions(self) -> int:
        return self._loaded.dimensions

    def embed(self, texts: list[str]) -> list[Vector]:
        return self._loaded.embed(texts)
