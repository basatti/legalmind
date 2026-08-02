"""Defers building an LLM provider until something actually needs a reply.

Mirrors embeddings/lazy.py exactly, for the same reason: constructing
CompanyLLMProvider reads COMPANY_API_URL/COMPANY_API_KEY from the environment,
and FastAPI resolves every declared dependency of a route before running its
handler — so without this, every request to /query/ask would need those
variables set, including requests that never reach retrieval or generation at
all (unauthenticated, validation-rejected, or authorised for nothing).
"""

from collections.abc import Callable

from services.llm import LLMProvider


class LazyLLMProvider(LLMProvider):
    """An LLMProvider that builds its delegate on first use."""

    def __init__(self, build: Callable[[], LLMProvider]) -> None:
        self._build = build
        self._delegate: LLMProvider | None = None

    def generate(self, prompt: str) -> str:
        if self._delegate is None:
            self._delegate = self._build()
        return self._delegate.generate(prompt)
