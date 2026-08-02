"""Ollama implementation of LLMProvider (LEG-63).

Runs a model on this machine, served over HTTP on localhost. No account, no
key, no per-question cost, and nothing leaves the machine — which is what makes
it usable with real case documents later, not only with sample text.

Model and host come from the environment, so trying a different model is a
config change rather than a code change.
"""

import os
from typing import Any

import httpx

from services.llm import LLMError, LLMProvider

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "aya-expanse:8b"
DEFAULT_TIMEOUT_SECONDS = 120.0


class OllamaLLMProvider(LLMProvider):
    """Talks to a locally served model.

    Accepts an injected transport so the request this builds can be inspected
    without a running server — the same reason BgeM3EmbeddingProvider accepts an
    injected encoder. Production code passes nothing and gets the real one.
    """

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
        self.host = (host or os.environ.get("OLLAMA_HOST", DEFAULT_HOST)).rstrip("/")
        self.timeout = timeout
        self._transport = transport

    def generate(self, prompt: str) -> str:
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        # Same reasoning as everywhere else: the same question
                        # over the same passages must give the same answer every
                        # time.
                        "options": {"temperature": 0.0},
                    },
                )
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Ollama at {self.host}: {exc}") from exc

        if response.status_code != 200:
            raise LLMError(f"Ollama returned {response.status_code}: {response.text[:300]}")

        return self._text(response.json())

    @staticmethod
    def _text(payload: Any) -> str:
        try:
            return str(payload["response"])
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected response shape: {payload}") from exc
