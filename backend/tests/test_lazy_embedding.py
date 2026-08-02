"""Tests for the lazy embedding wrapper (LEG-14 wiring)."""

from embeddings.base import EmbeddingProvider, Vector
from embeddings.lazy import LazyEmbeddingProvider


class CountingProvider(EmbeddingProvider):
    builds = 0

    def __init__(self) -> None:
        CountingProvider.builds += 1

    @property
    def dimensions(self) -> int:
        return 3

    def embed(self, texts: list[str]) -> list[Vector]:
        return [[1.0, 0.0, 0.0] for _ in texts]


def test_the_delegate_is_not_built_until_it_is_used() -> None:
    CountingProvider.builds = 0
    provider = LazyEmbeddingProvider(CountingProvider)

    print(f"after construction: {CountingProvider.builds} builds")
    assert CountingProvider.builds == 0

    provider.embed(["anything"])

    print(f"after embedding:    {CountingProvider.builds} builds")
    assert CountingProvider.builds == 1


def test_the_delegate_is_built_only_once() -> None:
    CountingProvider.builds = 0
    provider = LazyEmbeddingProvider(CountingProvider)

    provider.embed(["a"])
    provider.embed(["b"])
    assert provider.dimensions == 3

    assert CountingProvider.builds == 1
