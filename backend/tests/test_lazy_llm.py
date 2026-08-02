"""Tests for the lazy LLM wrapper (LEG-14 wiring)."""

from services.lazy_llm import LazyLLMProvider
from services.llm import LLMProvider


class CountingProvider(LLMProvider):
    builds = 0

    def __init__(self) -> None:
        CountingProvider.builds += 1

    def generate(self, prompt: str) -> str:
        return "reply"


def test_the_delegate_is_not_built_until_it_is_used() -> None:
    CountingProvider.builds = 0
    provider = LazyLLMProvider(CountingProvider)

    print(f"after construction: {CountingProvider.builds} builds")
    assert CountingProvider.builds == 0

    provider.generate("anything")

    print(f"after generating:   {CountingProvider.builds} builds")
    assert CountingProvider.builds == 1


def test_the_delegate_is_built_only_once() -> None:
    CountingProvider.builds = 0
    provider = LazyLLMProvider(CountingProvider)

    provider.generate("a")
    provider.generate("b")

    assert CountingProvider.builds == 1
